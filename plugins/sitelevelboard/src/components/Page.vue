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

const addOpen = ref(false)
const addSearch = ref('')
const addSelected = ref([])
const confirmTarget = ref(null)

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

async function req(method, path, body) {
  let raw
  if (props.api && typeof props.api[method] === 'function') {
    // 走宿主 api:相对 path(宿主已带 api/v1 前缀),见上方 REL_BASE 注释
    raw = await props.api[method](REL_BASE + path, body)
  } else {
    const res = await fetch(ABS_BASE + path, {
      method: method.toUpperCase(),
      credentials: 'include',
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    })
    raw = await res.json()
  }
  return unwrapResponse(raw)
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

/** 历史上传曲线(内联 SVG,不引第三方图表库)。 */
const spark = computed(() => {
  const hist = detail.value?.history || []
  if (hist.length < 2) return null
  const vals = hist.map(h => Number(h.upload_gb) || 0)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = Math.max(max - min, 1)
  const w = 100
  const h = 28
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w
    const y = h - ((v - min) / span) * h
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })
  return { points: pts.join(' '), min, max, w, h }
})

const timelineTrend = computed(() => {
  const hist = detail.value?.history || []
  if (hist.length < 2) return ''
  const a = hist[0]
  const b = hist[hist.length - 1]
  const du = (Number(b.upload_gb) || 0) - (Number(a.upload_gb) || 0)
  const dd = (Number(b.download_gb) || 0) - (Number(a.download_gb) || 0)
  const days = Math.max(hist.length - 1, 1)
  return `${a.day} → ${b.day}:上传 ${du >= 0 ? '+' : ''}${fmtGb(du)},下载 ${dd >= 0 ? '+' : ''}${fmtGb(dd)}`
    + `(日均 ${du >= 0 ? '+' : ''}${(du / days).toFixed(2)} GB / ${(dd / days).toFixed(2)} GB)`
})

function riskColor(risk) {
  return risk === 'danger' ? 'error' : risk === 'warn' ? 'warning' : 'success'
}

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
          <!-- 概要 -->
          <VCard variant="outlined" class="mb-3">
            <VCardText>
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
          </VCard>

          <VProgressLinear v-if="detailLoading" indeterminate color="primary" class="mb-3" />

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
                  <VIcon icon="mdi-shield-check-outline" start size="18" color="success" />保号状态与条件
                </VCardTitle>
                <VDivider />
                <VCardText class="text-body-2">
                  <div v-if="detail">
                    <div>可封存保号(封存后不会被删):<b>{{ detail.keep?.parkable_now ? '✅ 已达'
                      : (detail.keep?.levels_to_parkable !== null && detail.keep?.levels_to_parkable !== undefined
                        ? `还差 ${detail.keep.levels_to_parkable} 级` : '未知') }}</b></div>
                    <div>永久保留(不封存也不删):<b>{{ detail.keep?.permanent_now ? '✅ 已达'
                      : (detail.keep?.levels_to_permanent !== null && detail.keep?.levels_to_permanent !== undefined
                        ? `还差 ${detail.keep.levels_to_permanent} 级` : '未知') }}</b></div>
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

          <!-- 等级阶梯 -->
          <VCard v-if="detail?.ladder?.length" variant="outlined" class="mt-3 mb-3">
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

          <!-- 流量时间线 -->
          <VCard v-if="detail?.history?.length" variant="outlined">
            <VCardTitle class="text-subtitle-2 d-flex align-center">
              <VIcon icon="mdi-chart-line" start size="18" color="primary" />
              流量时间线(最近 {{ detail.history.length }} 天 · 来自 mp 的 siteuserdata 日快照)
            </VCardTitle>
            <VDivider />
            <VCardText>
              <div v-if="spark" class="mb-2">
                <svg :viewBox="`0 0 ${spark.w} ${spark.h}`" preserveAspectRatio="none"
                     style="width:100%;height:56px">
                  <polyline :points="spark.points" fill="none" stroke="rgb(var(--v-theme-primary))" stroke-width="1" />
                </svg>
                <div class="text-caption text-medium-emphasis">
                  上传曲线(纵轴 {{ fmtGb(spark.min) }} ~ {{ fmtGb(spark.max) }})
                </div>
              </div>
              <div class="text-caption mb-2">{{ timelineTrend }}</div>
              <VTable density="compact">
                <thead>
                  <tr>
                    <th>日期</th><th>上传</th><th>下载</th><th>分享率</th><th>魔力/积分</th><th>做种</th><th>做种体积</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in detail.history.slice(-14)" :key="h.day">
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
