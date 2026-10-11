<script setup>
/**
 * 站点等级看板 · 主界面(左侧站点列表 + 右侧等级详情)
 *
 * 宿主(MP)在渲染本组件时注入 ``api``(HTTP 客户端:get/post/put/delete);
 * 独立开发时没有 ``api``,自动退化为 fetch(带 cookie)。
 * 数据全部来自插件后端 11 个端点,契约见插件 __init__.py 顶部说明。
 */
import { computed, onMounted, ref } from 'vue'
import {
  CONFIDENCE_LABEL, SOURCE_LABEL, describeError, fmtEta, fmtGb, fmtNum, unwrapResponse,
} from '../utils'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'close'])

/**
 * ⚠️ 宿主(MP)注入的 ``api`` 客户端**自带前缀**:其 axios 实例 ``baseURL: 'api/v1/'``
 *    (见 MP 前端 bundles,「站点刷流」等插件同样按此约定调用)。
 *    所以传给它的必须是**相对 path** ``plugin/SiteLevelBoard/...``;
 *    若自己再叠一层 ``/api/v1`` 前缀,axios 会拼成 ``/api/v1/api/v1/...``
 *    → 前端报「Not Found」(2026-10-11 实际踩坑就是这个)。
 *    ``ABS_BASE`` 只在没有 ``api``(独立开发,退化为 fetch)时使用。
 */
const REL_BASE = 'plugin/SiteLevelBoard'
const ABS_BASE = `/api/v1/${REL_BASE}`

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const snack = ref({ show: false, text: '', color: 'success' })

const tracked = ref([])
const candidates = ref([])
const meta = ref({ last_refresh: null, snapshot_date: null })
const selectedId = ref(0)
const detail = ref(null)
const detailLoading = ref(false)

/**
 * 右侧详情分三个页签:等级概览 / 等级阶梯 / 流量趋势(与「站点刷流」同样的切法)。
 * 切换站点时**保留当前页签**(正在看阶梯,点下一个站点还停在阶梯);数据都由 /detail
 * 一次性返回,切页签不发请求。
 */
const activeTab = ref('overview')

const addOpen = ref(false)
const addSearch = ref('')
const addSelected = ref([])
const confirmTarget = ref(null)

const reportOpen = ref(false)
const reportText = ref('')
const reportLoading = ref(false)

const filteredCandidates = computed(() => {
  const kw = addSearch.value.trim().toLowerCase()
  if (!kw) return candidates.value
  return candidates.value.filter(
    item => `${item.name} ${item.domain}`.toLowerCase().includes(kw),
  )
})

const current = computed(() => tracked.value.find(item => item.id === selectedId.value) || null)

function toast(text, color = 'success') {
  snack.value = { show: true, text, color }
}

/** 发请求,拿**原始响应体**(有些端点把文本放在 message 里,比如 /report)。 */
async function rawReq(method, path, body) {
  if (props.api && typeof props.api[method] === 'function') {
    // 走宿主 api:相对 path(宿主已带 api/v1 前缀),见上方 REL_BASE 注释
    return await props.api[method](REL_BASE + path, body)
  }
  const res = await fetch(ABS_BASE + path, {
    method: method.toUpperCase(),
    credentials: 'include',
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  return await res.json()
}

async function req(method, path, body) {
  return unwrapResponse(await rawReq(method, path, body))
}

async function loadSites(keepSelection = true) {
  loading.value = true
  error.value = ''
  try {
    const data = await req('get', '/sites')
    tracked.value = data.tracked || []
    candidates.value = data.candidates || []
    meta.value = { last_refresh: data.last_refresh, snapshot_date: data.snapshot_date }
    const exists = tracked.value.some(item => item.id === selectedId.value)
    if (!keepSelection || !exists) {
      selectedId.value = tracked.value.length ? tracked.value[0].id : 0
    }
    if (selectedId.value) await loadDetail(selectedId.value)
    else detail.value = null
  } catch (e) {
    error.value = describeError(e)
  } finally {
    loading.value = false
  }
}

async function loadDetail(siteId) {
  if (!siteId) return
  detailLoading.value = true
  try {
    detail.value = await req('get', `/detail?site_id=${siteId}`)
  } catch (e) {
    detail.value = null
    error.value = describeError(e)
  } finally {
    detailLoading.value = false
  }
}

function selectSite(id) {
  if (selectedId.value === id) return
  selectedId.value = id
  loadDetail(id)
}

async function refreshAll() {
  busy.value = true
  try {
    await req('post', '/refresh', {})
    toast('已开始全量刷新,稍后自动更新列表', 'info')
    // 后台刷新约 10~60 秒;这里做一次延迟重取 + 允许手动再点
    setTimeout(() => loadSites(true), 12000)
    setTimeout(() => loadSites(true), 40000)
  } catch (e) {
    toast(describeError(e), 'error')
  } finally {
    busy.value = false
  }
}

async function refreshOne() {
  const site = current.value
  if (!site) return
  busy.value = true
  try {
    const data = await req('post', '/refresh', { site_id: site.id })
    detail.value = data
    await loadSites(true)
    toast('已刷新该站点', 'success')
  } catch (e) {
    toast(describeError(e), 'error')
  } finally {
    busy.value = false
  }
}

function openAdd() {
  addSearch.value = ''
  addSelected.value = []
  addOpen.value = true
}

async function submitAdd() {
  if (!addSelected.value.length) {
    toast('请先勾选要加入的站点', 'warning')
    return
  }
  busy.value = true
  try {
    await req('post', '/track', { site_ids: addSelected.value })
    addOpen.value = false
    await loadSites(true)
    toast(`已加入 ${addSelected.value.length} 个站点`, 'success')
  } catch (e) {
    toast(describeError(e), 'error')
  } finally {
    busy.value = false
  }
}

async function doRemove(site) {
  busy.value = true
  try {
    await req('post', '/untrack', { site_id: site.id })
    confirmTarget.value = null
    if (selectedId.value === site.id) {
      detail.value = null
      selectedId.value = 0
    }
    await loadSites(false)
    toast(`已把「${site.name}」移出看板(不影响 mp 站点管理)`, 'info')
  } catch (e) {
    toast(describeError(e), 'error')
  } finally {
    busy.value = false
  }
}

/**
 * 复制汇总:取 /report 的文字版(全站等级/条件/风险),弹窗里可全选、一键复制。
 * 注意 /report 把文本放在 message 里(不是 data),所以这里用 rawReq 取原始响应。
 */
async function loadReport() {
  reportLoading.value = true
  try {
    const raw = await rawReq('get', '/report')
    const text = String((raw && (raw.message || raw.data)) || '').trim()
    reportText.value = text || '(暂无内容:先在插件里刷新一次数据)'
    reportOpen.value = true
  } catch (e) {
    toast(describeError(e), 'error')
  } finally {
    reportLoading.value = false
  }
}

async function copyReport() {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(reportText.value)
    } else {
      // http 页面不是安全上下文,没有 clipboard API → 退回隐藏 textarea + execCommand
      const area = document.createElement('textarea')
      area.value = reportText.value
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      document.body.removeChild(area)
    }
    toast('已复制到剪贴板', 'success')
    reportOpen.value = false
  } catch (e) {
    toast('复制失败,可在弹窗里手动全选复制', 'warning')
  }
}

/**
 * 左侧列表拖拽排序:用原生 HTML5 DnD,不引第三方库(vuedraggable 没在宿主 shared 里,
 * 自己打包一份不划算)。落点用 dragIndex/overIndex 标出插入线,松手后先本地生效、
 * 再 POST /reorder 落库;失败就把顺序回滚,避免界面与后端不一致。
 */
const dragIndex = ref(-1)
const overIndex = ref(-1)

function onDragStart(index, event) {
  dragIndex.value = index
  overIndex.value = index
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(tracked.value[index]?.id ?? ''))
  }
}

function onDragOver(index) {
  if (dragIndex.value >= 0) overIndex.value = index
}

async function onDrop(index) {
  const from = dragIndex.value
  dragIndex.value = -1
  overIndex.value = -1
  if (from < 0 || from === index) return
  const before = tracked.value.slice()
  const list = tracked.value.slice()
  const [moved] = list.splice(from, 1)
  list.splice(index, 0, moved)
  tracked.value = list
  try {
    await req('post', '/reorder', { site_ids: list.map(x => x.id) })
  } catch (e) {
    tracked.value = before
    toast(describeError(e), 'error')
  }
}

function onDragEnd() {
  dragIndex.value = -1
  overIndex.value = -1
}

/** 趋势可选指标(键名 = /detail 里 history 的字段)。 */
const TRAFFIC_METRICS = [
  { key: 'upload_gb', label: '上传', fmt: v => fmtGb(v) },
  { key: 'download_gb', label: '下载', fmt: v => fmtGb(v) },
  { key: 'ratio', label: '分享率', fmt: v => fmtNum(v, 3) },
  { key: 'bonus', label: '魔力/积分', fmt: v => fmtNum(v, 1) },
  { key: 'seeding_size_gb', label: '做种体积', fmt: v => fmtGb(v) },
  { key: 'seeding', label: '做种数', fmt: v => fmtNum(v, 0) },
]
const trafficMetric = ref('upload_gb')
const trafficRange = ref(14)
const trafficHover = ref(-1)

const trafficRows = computed(() => (detail.value?.history || []).slice(-trafficRange.value))
const trafficMetricDef = computed(
  () => TRAFFIC_METRICS.find(m => m.key === trafficMetric.value) || TRAFFIC_METRICS[0],
)

/** 内联 SVG 折线(不引第三方图表库;纵轴按当前指标自适应)。 */
const trafficChart = computed(() => {
  const rows = trafficRows.value
  if (rows.length < 2) return null
  const vals = rows.map(h => Number(h[trafficMetric.value]) || 0)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = Math.max(max - min, 1)
  const w = 100
  const h = 28
  const points = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w
    const y = h - ((v - min) / span) * h
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })
  return { min, max, w, h, points: points.join(' ') }
})

/** 鼠标在图上移动 → 定位到最近的采样日,读出当天数值。 */
function onChartMove(event) {
  const rows = trafficRows.value
  if (!rows.length || !trafficChart.value) return
  const rect = event.currentTarget.getBoundingClientRect()
  const ratio = Math.min(Math.max((event.clientX - rect.left) / rect.width, 0), 1)
  trafficHover.value = Math.round(ratio * (rows.length - 1))
}

/** 区间变化一行:按当前指标与范围算首末差 + 日均。 */
const trafficTrend = computed(() => {
  const rows = trafficRows.value
  if (rows.length < 2) return ''
  const key = trafficMetric.value
  const def = trafficMetricDef.value
  const first = Number(rows[0][key]) || 0
  const last = Number(rows[rows.length - 1][key]) || 0
  const delta = last - first
  const perDay = delta / Math.max(rows.length - 1, 1)
  const sign = v => (v >= 0 ? '+' : '')
  return `${rows[0].day} → ${rows[rows.length - 1].day}:${def.label} ${sign(delta)}${def.fmt(delta)}`
    + ` · 日均 ${sign(perDay)}${def.fmt(perDay)}`
})

/**
 * 「最紧条件」——与后端 __progress 同一口径:取未达成条件里 当前/目标 最小的那个,
 * 让「到底卡在哪一项」直接写在脸上(进度条只给了个百分比)。
 */
const tightest = computed(() => {
  const unmet = (detail.value?.reqs || []).filter(r => !r.met)
  if (!unmet.length) return null
  const ratio = r => (r.target && typeof r.current === 'number' && r.target > 0
    ? Math.min(1, r.current / r.target) : null)
  const scored = unmet.map(r => ({ r, v: ratio(r) })).filter(x => x.v !== null)
  if (!scored.length) return unmet[0]
  return scored.reduce((a, b) => (b.v < a.v ? b : a)).r
})

/** 全站风险汇总:数据来自 /sites(每站的 risk 由后端算好),点站点名可跳到该站。 */
const riskSummary = computed(() => ({
  danger: tracked.value.filter(s => s.risk === 'danger'),
  warn: tracked.value.filter(s => s.risk === 'warn'),
}))

/** 保号路线图(后端 roadmap:到「可封存 / 永久保留」档还差几级、照当前增速多久、卡在哪)。 */
const roadmapRows = computed(() => {
  const rm = detail.value?.roadmap || {}
  return [
    { key: 'parkable', label: '可封存保号', icon: 'mdi-shield-lock-outline', tone: 'success', data: rm.parkable },
    { key: 'permanent', label: '永久保留', icon: 'mdi-shield-star-outline', tone: 'primary', data: rm.permanent },
  ].filter(row => row.data)
})

function roadmapAway(m) {
  if (!m) return ''
  if (m.reached) return '已达成'
  return `还差 ${m.levels_away} 级${m.name ? ` → ${m.name}` : ''}`
}

function roadmapEta(m) {
  if (!m) return ''
  if (m.reached) return '✅'
  const hasEta = m.eta_days !== null && m.eta_days !== undefined
  if (m.blockers?.length) {
    if (!hasEta) return '暂不可估'
    if (m.eta_days <= 0) return '其余条件已就位,只差卡点'
    return `最快 ${fmtEta(m.eta_days)}(仅按可推算条件)`
  }
  return hasEta ? `${fmtEta(m.eta_days)}(${CONFIDENCE_LABEL[m.confidence] || '?'})` : '暂不可估'
}

function roadmapBlocker(m) {
  return (m?.blockers || []).map(b => {
    const kind = b.kind === 'manual' ? '需人为推动' : '数据不足'
    const cur = (b.current === null || b.current === undefined) ? null : fmtNum(b.current)
    const target = `${fmtNum(b.target)}${b.unit || ''}`
    return cur === null ? `${b.label}(${kind})` : `${b.label}:当前 ${cur} / 目标 ${target}(${kind})`
  }).join(' · ')
}

function riskColor(risk) {
  return risk === 'danger' ? 'error' : risk === 'warn' ? 'warning' : 'success'
}

/** 当前站点有没有风险 —— 显示成「等级概览」页签上的小圆点,人在别的页签也能看见。 */
const riskLevel = computed(() => {
  const risks = detail.value?.risks || []
  if (risks.some(r => r.level === 'danger')) return 'danger'
  return risks.length ? 'warn' : ''
})

function etaText(site) {
  if (site.manual_blocked) return '受人为条件限制'
  if (site.eta_days === null || site.eta_days === undefined) {
    return site.next_level ? '无法估算' : '已最高/无规则'
  }
  return `${fmtEta(site.eta_days)}(${CONFIDENCE_LABEL[site.confidence] || '?'})`
}

onMounted(() => loadSites(true))
</script>

<template>
  <VContainer fluid class="pa-4">
    <!-- 顶部 -->
    <VRow dense align="center" class="mb-2">
      <VCol cols="auto">
        <VIcon icon="mdi-account-star-outline" color="primary" size="28" />
      </VCol>
      <VCol>
        <div class="text-h6">站点等级看板</div>
        <div class="text-caption text-medium-emphasis">
          上次刷新:{{ meta.last_refresh || '从未' }} · 内置等级规则快照:{{ meta.snapshot_date || '-' }}
          · 看板站点 {{ tracked.length }} 个
        </div>
      </VCol>
      <VCol cols="auto">
        <VBtn size="small" variant="text" prepend-icon="mdi-file-document-outline"
              :loading="reportLoading" @click="loadReport">
          复制汇总
        </VBtn>
        <VBtn size="small" variant="tonal" prepend-icon="mdi-refresh" :loading="busy" @click="refreshAll">
          刷新全部
        </VBtn>
      </VCol>
    </VRow>

    <VAlert v-if="error" type="error" variant="tonal" density="compact" class="mb-3" closable @click:close="error = ''">
      {{ error }}
    </VAlert>

    <VRow>
      <!-- ============ 左:站点列表 ============ -->
      <VCol cols="12" md="3">
        <!-- 全站风险汇总:一眼看全站有没有要处理的,点名字跳过去 -->
        <VCard v-if="tracked.length" variant="tonal" class="mb-3"
               :color="riskSummary.danger.length ? 'error' : (riskSummary.warn.length ? 'warning' : 'success')">
          <VCardText class="py-2 text-caption">
            <template v-if="riskSummary.danger.length || riskSummary.warn.length">
              <b>风险汇总</b>
              <span v-if="riskSummary.danger.length" class="ml-1">⛔ {{ riskSummary.danger.length }}</span>
              <span v-if="riskSummary.warn.length" class="ml-1">⚠️ {{ riskSummary.warn.length }}</span>
              <div class="mt-1">
                <VChip v-for="s in [...riskSummary.danger, ...riskSummary.warn]" :key="'risk' + s.id"
                       size="x-small" variant="flat" class="mr-1 mb-1" @click="selectSite(s.id)">
                  {{ s.name }}
                </VChip>
              </div>
            </template>
            <template v-else>
              ✅ {{ tracked.length }} 个站点均无风险提示
            </template>
          </VCardText>
        </VCard>

        <VCard variant="outlined">
          <VCardTitle class="text-subtitle-2 d-flex align-center">
            <VIcon icon="mdi-server-network" start size="18" color="primary" />站点({{ tracked.length }})
            <VSpacer />
            <span v-if="tracked.length > 1" class="text-caption text-medium-emphasis font-weight-regular">
              <VIcon icon="mdi-drag-vertical" size="14" />拖动排序
            </span>
          </VCardTitle>
          <VDivider />
          <VList v-if="tracked.length" density="compact" nav class="py-0">
            <VListItem
              v-for="(s, i) in tracked"
              :key="s.id"
              :active="s.id === selectedId"
              color="primary"
              draggable="true"
              :class="[
                'slb-item',
                dragIndex === i ? 'slb-dragging' : '',
                overIndex === i && dragIndex >= 0 && dragIndex !== i
                  ? (dragIndex > i ? 'slb-drop-above' : 'slb-drop-below') : '',
              ]"
              @click="selectSite(s.id)"
              @dragstart="onDragStart(i, $event)"
              @dragover.prevent="onDragOver(i)"
              @drop.prevent.stop="onDrop(i)"
              @dragend="onDragEnd"
            >
              <template #prepend>
                <VIcon icon="mdi-circle" size="10" :color="riskColor(s.risk)" />
              </template>
              <VListItemTitle class="text-body-2">
                {{ s.name }}
                <VChip size="x-small" variant="tonal" class="ml-1">{{ s.level || '?' }}</VChip>
              </VListItemTitle>
              <VListItemSubtitle class="text-caption">
                {{ s.domain }}
                <span v-if="!s.evaluated" class="text-warning"> · 未评估</span>
              </VListItemSubtitle>
              <template #append>
                <VBtn
                  icon="mdi-delete-outline"
                  size="x-small"
                  variant="text"
                  color="error"
                  title="移出看板"
                  @click.stop="confirmTarget = s"
                />
              </template>
            </VListItem>
          </VList>
          <div v-else class="pa-3 text-caption text-medium-emphasis">
            还没有站点。点下方「新增站点」从你的 mp 站点里挑。
          </div>
          <VDivider />
          <div class="pa-3">
            <VBtn block variant="tonal" prepend-icon="mdi-plus" @click="openAdd">新增站点</VBtn>
          </div>
        </VCard>

        <VCard variant="outlined" class="mt-3">
          <VCardText class="text-caption text-medium-emphasis">
            圆点含义:<VIcon icon="mdi-circle" size="10" color="success" /> 正常 ·
            <VIcon icon="mdi-circle" size="10" color="warning" /> 有提示 ·
            <VIcon icon="mdi-circle" size="10" color="error" /> 有硬风险
          </VCardText>
        </VCard>
      </VCol>

      <!-- ============ 右:等级详情 ============ -->
      <VCol cols="12" md="9">
        <VCard v-if="!selectedId" variant="outlined">
          <VCardText class="text-medium-emphasis">从左侧选择一个站点,这里会显示它的等级统计。</VCardText>
        </VCard>

        <template v-else>
          <!-- 常驻状态条:站点名 / 等级 → 下一级 / ETA / 进度;页签只切下半部分 -->
          <VCard variant="outlined" class="mb-3">
            <VCardText class="pb-0">
              <div class="d-flex align-center flex-wrap ga-2 mb-2">
                <span class="text-h6">{{ detail?.site_name || current?.name }}</span>
                <VChip color="primary" variant="tonal">{{ detail?.level || '?' }}</VChip>
                <VIcon icon="mdi-arrow-right" size="18" />
                <VChip variant="outlined">{{ detail?.next_level || '未知/已最高' }}</VChip>
                <VChip v-if="detail" :color="detail.manual_blocked ? 'warning' : 'success'" variant="tonal">
                  {{ etaText(detail) }}
                </VChip>
                <VSpacer />
                <VBtn size="x-small" variant="text" prepend-icon="mdi-refresh" :loading="busy" @click="refreshOne">
                  刷新本站
                </VBtn>
                <VBtn v-if="detail?.site_url" size="x-small" variant="text" prepend-icon="mdi-open-in-new"
                      :href="detail.site_url" target="_blank">打开站点</VBtn>
              </div>
              <VProgressLinear
                v-if="detail && detail.progress_pct !== null && detail.progress_pct !== undefined"
                :model-value="detail.progress_pct"
                height="10"
                rounded
                color="primary"
                class="mb-2"
              />
              <div class="text-caption text-medium-emphasis">
                <span v-if="detail">
                  晋级进度按「最紧条件」计 {{ detail.progress_pct ?? 0 }}%
                  · 数据来源:{{ SOURCE_LABEL[detail.source] || detail.source || '-' }}
                  <span v-if="detail.source === 'ptd_snapshot'">(快照 {{ detail.snapshot_date }})</span>
                  · siteuserdata 更新于 {{ detail.l1_updated || '-' }}
                </span>
              </div>
            </VCardText>
            <VTabs v-model="activeTab" color="primary" density="comfortable" class="slb-tabs">
              <VTab value="overview">
                等级概览
                <VIcon v-if="riskLevel" icon="mdi-circle" size="10" :color="riskColor(riskLevel)" class="ml-1" />
              </VTab>
              <VTab value="ladder">等级阶梯</VTab>
              <VTab value="traffic">流量趋势</VTab>
            </VTabs>
          </VCard>

          <VProgressLinear v-if="detailLoading" indeterminate color="primary" class="mb-3" />

          <template v-if="activeTab === 'overview'">
          <!-- 最紧条件:把「到底卡在哪一项」写在最前面 -->
          <VCard v-if="tightest" variant="outlined" class="mb-3">
            <VCardTitle class="text-subtitle-2 d-flex align-center">
              <VIcon icon="mdi-target" start size="18" color="primary" />卡住晋级的是
            </VCardTitle>
            <VDivider />
            <VCardText class="text-body-2">
              <div class="mb-1 font-weight-medium">{{ tightest.label }}</div>
              <div class="text-caption text-medium-emphasis">
                当前 {{ tightest.current === null ? '取不到' : fmtNum(tightest.current) + tightest.unit }}
                → 目标 {{ fmtNum(tightest.target) }}{{ tightest.unit }}
                <template v-if="typeof tightest.current === 'number' && tightest.target">
                  · 还差 {{ fmtNum(Math.max(0, tightest.target - tightest.current)) }}{{ tightest.unit }}
                </template>
                · {{ tightest.eta_days !== null && tightest.eta_days !== undefined
                  ? `${tightest.rate_label || ''} → ${fmtEta(tightest.eta_days)}`
                  : (tightest.eta_kind === 'manual' ? '需人为推动,光等不会达成' : '趋势不足(攒够样本后可估)') }}
              </div>
            </VCardText>
          </VCard>
          <VAlert v-else-if="detail?.reqs?.length" type="success" variant="tonal" density="compact" class="mb-3">
            当前等级的自动条件已全部达成 ✅<span v-if="detail.manual_blocked">;仍有人为条件需要推进</span>
          </VAlert>

          <!-- 下一级条件 -->
          <VCard v-if="detail?.reqs?.length" variant="outlined" class="mb-3">
            <VCardTitle class="text-subtitle-2 d-flex align-center">
              <VIcon icon="mdi-checkbox-marked-circle-outline" start size="18" color="primary" />
              下一级条件(已达成 {{ detail.reqs.filter(r => r.met).length }} / {{ detail.reqs.length }})
            </VCardTitle>
            <VDivider />
            <VTable density="compact">
              <thead>
                <tr>
                  <th style="width:46px">状态</th>
                  <th>条件</th>
                  <th style="width:120px">目标</th>
                  <th style="width:120px">当前</th>
                  <th style="width:190px">增速 / 预计</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in detail.reqs" :key="r.key" :class="{ 'text-medium-emphasis': r.met }">
                  <td>
                    <VIcon :icon="r.met ? 'mdi-check-circle' : 'mdi-close-circle'"
                           :color="r.met ? 'success' : 'error'" size="18" />
                  </td>
                  <td>{{ r.label }}</td>
                  <td>{{ fmtNum(r.target) }}{{ r.unit }}</td>
                  <td>{{ r.current === null ? '取不到' : fmtNum(r.current) + r.unit }}</td>
                  <td>
                    <span v-if="r.met">已达成</span>
                    <span v-else-if="r.eta_days !== null && r.eta_days !== undefined">
                      {{ r.rate_label || '' }} → {{ fmtEta(r.eta_days) }}
                    </span>
                    <span v-else>{{ r.rate_label || (r.eta_kind === 'manual' ? '需人为推动' : '趋势不足') }}</span>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
          <VAlert v-else-if="detail && !detail.reqs?.length" type="info" variant="tonal" density="compact" class="mb-3">
            该站没有可解析的晋级条件(站点未公开门槛,可在插件配置里用「手动规则」补),以下仍显示当前等级与保号信息。
          </VAlert>

          <!-- 保号 / 封号 -->
          <VRow class="mb-1">
            <VCol cols="12" md="6">
              <VCard variant="outlined" class="h-100">
                <VCardTitle class="text-subtitle-2 d-flex align-center">
                  <VIcon icon="mdi-shield-check-outline" start size="18" color="success" />保号状态与路线
                </VCardTitle>
                <VDivider />
                <VCardText class="text-body-2">
                  <div v-if="detail">
                    <div v-for="row in roadmapRows" :key="row.key" class="mb-2">
                      <div class="d-flex align-center flex-wrap">
                        <VIcon :icon="row.icon" size="16" :color="row.tone" class="mr-1" />
                        <b>{{ row.label }}</b>
                        <span class="ml-1 text-medium-emphasis">{{ roadmapAway(row.data) }}</span>
                        <VSpacer />
                        <span class="text-caption">{{ roadmapEta(row.data) }}</span>
                      </div>
                      <div v-if="roadmapBlocker(row.data)" class="text-caption text-warning ml-5">
                        卡点:{{ roadmapBlocker(row.data) }}
                      </div>
                    </div>
                    <div v-if="!roadmapRows.length" class="text-medium-emphasis mb-2">
                      该站规则里没有保号档信息(仍可看下面的条款原文)
                    </div>
                    <VDivider class="my-2" />
                    <div v-for="(t, i) in detail.keep_rules || []" :key="'k' + i">✅ {{ t }}</div>
                    <div v-if="!(detail.keep_rules || []).length" class="text-medium-emphasis">站点未提供保号条款</div>
                  </div>
                </VCardText>
              </VCard>
            </VCol>
            <VCol cols="12" md="6">
              <VCard variant="outlined" class="h-100">
                <VCardTitle class="text-subtitle-2 d-flex align-center">
                  <VIcon icon="mdi-alert-octagon-outline" start size="18" color="error" />封号 / 降级条款
                </VCardTitle>
                <VDivider />
                <VCardText class="text-body-2">
                  <div v-for="(t, i) in detail?.ban_rules || []" :key="'b' + i" class="mb-1">⛔ {{ t }}</div>
                  <div v-if="!detail?.ban_rules?.length" class="text-medium-emphasis">
                    站点未提供(或不在公开页面)——请以站点公告为准
                  </div>
                  <template v-if="detail?.risks?.length">
                    <VDivider class="my-2" />
                    <div v-for="(r, i) in detail.risks" :key="'r' + i"
                         :class="r.level === 'danger' ? 'text-error' : 'text-warning'">
                      {{ r.level === 'danger' ? '🔴' : '⚠️' }} {{ r.text }}
                    </div>
                  </template>
                </VCardText>
              </VCard>
            </VCol>
          </VRow>
          </template>

          <!-- ============ 页签二:全部等级阶梯 ============ -->
          <template v-else-if="activeTab === 'ladder'">
          <VCard v-if="detail?.ladder?.length" variant="outlined" class="mb-3">
            <VCardTitle class="text-subtitle-2 d-flex align-center">
              <VIcon icon="mdi-stairs" start size="18" color="primary" />全部等级阶梯
              <VSpacer />
              <span class="text-caption text-medium-emphasis">🏅 永久保号 · 🔒 可封存保号</span>
            </VCardTitle>
            <VDivider />
            <VTable density="compact">
              <thead>
                <tr>
                  <th style="width:150px">等级</th>
                  <th>晋级条件</th>
                  <th style="width:150px">特权 / 备注</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="lv in detail.ladder" :key="lv.order"
                    :class="{ 'bg-primary': lv.order === detail.level_order, 'font-weight-bold': lv.order === detail.next_order }">
                  <td>
                    <span class="mr-1">{{ lv.order }}</span>{{ lv.name }}
                    <span v-if="lv.is_permanent">🏅</span>
                    <span v-if="lv.is_parkable">🔒</span>
                    <VChip v-if="lv.order === detail.level_order" size="x-small" color="primary" class="ml-1">当前</VChip>
                    <VChip v-else-if="lv.order === detail.next_order" size="x-small" variant="outlined" class="ml-1">下一级</VChip>
                  </td>
                  <td class="text-caption">
                    <span v-if="!lv.requirements.length" class="text-medium-emphasis">默认/无自动条件</span>
                    <span v-else>{{ lv.requirements.map(r => r.label).join(' · ') }}</span>
                    <span v-if="lv.demote_ratio" class="text-error"> (分享率 &lt; {{ lv.demote_ratio }} 降级)</span>
                  </td>
                  <td class="text-caption">{{ lv.privilege || '-' }}</td>
                </tr>
              </tbody>
            </VTable>
          </VCard>
          <VAlert v-else type="info" variant="tonal" density="compact">
            该站没有可解析的等级阶梯 —— 站点未公开等级规则,可在插件配置里用「手动规则」补。
          </VAlert>
          </template>

          <!-- ============ 页签三:流量趋势 ============ -->
          <template v-else>
          <VCard v-if="detail?.history?.length" variant="outlined" class="mb-3">
            <VCardTitle class="text-subtitle-2 d-flex align-center">
              <VIcon icon="mdi-chart-line" start size="18" color="primary" />
              流量趋势
              <VSpacer />
              <span class="text-caption text-medium-emphasis">来自 mp 的 siteuserdata 日快照</span>
            </VCardTitle>
            <VDivider />
            <VCardText>
              <div class="d-flex align-center flex-wrap ga-2 mb-2">
                <VBtnToggle v-model="trafficMetric" density="compact" variant="outlined" divided mandatory>
                  <VBtn v-for="m in TRAFFIC_METRICS" :key="m.key" :value="m.key" size="small">{{ m.label }}</VBtn>
                </VBtnToggle>
                <VSpacer />
                <VBtnToggle v-model="trafficRange" density="compact" variant="outlined" divided mandatory>
                  <VBtn :value="7" size="small">7 天</VBtn>
                  <VBtn :value="14" size="small">14 天</VBtn>
                  <VBtn :value="30" size="small">30 天</VBtn>
                </VBtnToggle>
              </div>
              <div v-if="trafficChart" class="slb-chart" @mousemove="onChartMove" @mouseleave="trafficHover = -1">
                <svg :viewBox="`0 0 ${trafficChart.w} ${trafficChart.h}`" preserveAspectRatio="none">
                  <polyline :points="trafficChart.points" fill="none"
                            stroke="rgb(var(--v-theme-primary))" stroke-width="0.8"
                            vector-effect="non-scaling-stroke" />
                </svg>
              </div>
              <div class="text-caption mt-1 mb-2">
                <template v-if="trafficHover >= 0 && trafficRows[trafficHover]">
                  {{ trafficRows[trafficHover].day }} · {{ trafficMetricDef.label }}
                  <b>{{ trafficMetricDef.fmt(Number(trafficRows[trafficHover][trafficMetric]) || 0) }}</b>
                </template>
                <span v-else-if="trafficChart" class="text-medium-emphasis">
                  纵轴 {{ trafficMetricDef.fmt(trafficChart.min) }} ~ {{ trafficMetricDef.fmt(trafficChart.max) }}
                  · 鼠标移到曲线上可读某天数值
                </span>
              </div>
              <div class="text-caption mb-2">{{ trafficTrend }}</div>
              <VTable density="compact">
                <thead>
                  <tr>
                    <th>日期</th><th>上传</th><th>下载</th><th>分享率</th><th>魔力/积分</th><th>做种</th><th>做种体积</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in trafficRows" :key="h.day">
                    <td>{{ h.day }}</td>
                    <td>{{ fmtGb(h.upload_gb) }}</td>
                    <td>{{ fmtGb(h.download_gb) }}</td>
                    <td>{{ fmtNum(h.ratio, 3) }}</td>
                    <td>{{ fmtNum(h.bonus, 1) }}</td>
                    <td>{{ h.seeding ?? '-' }}</td>
                    <td>{{ fmtGb(h.seeding_size_gb) }}</td>
                  </tr>
                </tbody>
              </VTable>
            </VCardText>
          </VCard>
          <VAlert v-else type="info" variant="tonal" density="compact">
            还没有历史快照 —— mp 的 siteuserdata 每天更新一行,攒几天后这里会出现曲线。
          </VAlert>
          </template>
        </template>
      </VCol>
    </VRow>

    <!-- 新增站点弹窗 -->
    <VDialog v-model="addOpen" max-width="640" scrollable>
      <VCard>
        <VCardTitle class="text-subtitle-1 d-flex align-center">
          <VIcon icon="mdi-plus-circle-outline" start color="primary" />新增站点到看板
        </VCardTitle>
        <VDivider />
        <VCardText>
          <VTextField v-model="addSearch" density="compact" variant="outlined" hide-details
                      prepend-inner-icon="mdi-magnify" label="筛选站点(名称或域名)" class="mb-3" />
          <div v-if="!filteredCandidates.length" class="text-caption text-medium-emphasis">
            没有可添加的站点(要么都已在看板里,要么 mp 里还没绑定站点)
          </div>
          <VList v-else density="compact" class="py-0">
            <VListItem v-for="c in filteredCandidates" :key="c.id" @click="addSelected.includes(c.id)
              ? (addSelected = addSelected.filter(x => x !== c.id))
              : addSelected.push(c.id)">
              <template #prepend>
                <VCheckboxBtn :model-value="addSelected.includes(c.id)" color="primary" />
              </template>
              <VListItemTitle class="text-body-2">{{ c.name }}</VListItemTitle>
              <VListItemSubtitle class="text-caption">{{ c.domain }}</VListItemSubtitle>
            </VListItem>
          </VList>
        </VCardText>
        <VDivider />
        <VCardActions>
          <div class="text-caption text-medium-emphasis ml-2">已选 {{ addSelected.length }} 个</div>
          <VSpacer />
          <VBtn variant="text" @click="addOpen = false">取消</VBtn>
          <VBtn color="primary" variant="flat" :loading="busy" @click="submitAdd">加入看板</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- 移出确认 -->
    <VDialog :model-value="!!confirmTarget" max-width="420" @update:model-value="confirmTarget = null">
      <VCard>
        <VCardTitle class="text-subtitle-1">移出看板?</VCardTitle>
        <VCardText class="text-body-2">
          将把「{{ confirmTarget?.name }}」从本站点看板里移除 —— <b>不会</b>删除 mp 里的站点配置,之后还能再添加回来。
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirmTarget = null">取消</VBtn>
          <VBtn color="error" variant="flat" :loading="busy" @click="doRemove(confirmTarget)">移出</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- 复制汇总:取 /report 的文字版,弹窗里可全选、一键复制 -->
    <VDialog v-model="reportOpen" max-width="760" scrollable>
      <VCard>
        <VCardTitle class="text-subtitle-1 d-flex align-center">
          <VIcon icon="mdi-file-document-outline" start color="primary" />等级汇总(可复制)
        </VCardTitle>
        <VDivider />
        <VCardText>
          <VTextarea v-model="reportText" readonly variant="outlined" rows="18" hide-details
                     class="slb-report" />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="reportOpen = false">关闭</VBtn>
          <VBtn color="primary" variant="flat" prepend-icon="mdi-content-copy" @click="copyReport">复制</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <VSnackbar v-model="snack.show" :color="snack.color" :timeout="3000" location="bottom">
      {{ snack.text }}
    </VSnackbar>
  </VContainer>
</template>

<style scoped>
/* 只做微调;主题色/间距一律沿用宿主 Vuetify 主题 */
.bg-primary tr td,
tr.bg-primary td {
  background: rgba(var(--v-theme-primary), 0.12);
}

/* 右侧页签:贴着状态条底部,与内容区用同一条分隔线 */
.slb-tabs {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* 流量趋势曲线:撑满宽度、鼠标可读数值 */
.slb-chart {
  cursor: crosshair;
}
.slb-chart svg {
  display: block;
  width: 100%;
  height: 64px;
}

/* 汇总文本:等宽字体,便于阅读对齐 */
.slb-report :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

/* 左侧站点列表:可拖动 + 插入位置提示 */
.slb-item {
  cursor: grab;
}
.slb-item.slb-dragging {
  opacity: 0.4;
}
.slb-item.slb-drop-above {
  box-shadow: inset 0 2px 0 0 rgb(var(--v-theme-primary));
}
.slb-item.slb-drop-below {
  box-shadow: inset 0 -2px 0 0 rgb(var(--v-theme-primary));
}
</style>
