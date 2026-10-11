<script setup>
/**
 * 站点等级看板 · 配置页(Vue 版)
 *
 * 与声明式 ``get_form`` 共用同一份配置(后端 `/config`、`/config/save`),
 * 保存会走 MP 的 PluginConfigCommand.update(保存 + 重新初始化 + 刷新调度)。
 */
import { onMounted, ref } from 'vue'
import { describeError, unwrapResponse } from '../utils'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action', 'close'])

// 宿主 api 客户端自带 `api/v1/` 前缀 → 只能传相对 path(详见 Page.vue 顶部注释);
// ABS_BASE 仅供独立开发(无 api prop,退化为 fetch)使用。
const REL_BASE = 'plugin/SiteLevelBoard'
const ABS_BASE = `/api/v1/${REL_BASE}`
const saving = ref(false)
const loading = ref(true)
const message = ref('')
const messageType = ref('success')

const form = ref({
  enabled: false,
  run_once: false,
  cron: '45 8 * * *',
  notify: true,
  notify_daily: true,
  notify_level_change: true,
  notify_risk: true,
  notify_eta: false,
  eta_threshold_days: 7,
  notify_channel: '',
  quiet_start: '',
  quiet_end: '',
  prefer_source: 'site_page',
  use_site_page: true,
  timeout: 20,
  manual_first: false,
  manual_rules: '',
  debug: false,
})

async function req(method, path, body) {
  let raw
  if (props.api && typeof props.api[method] === 'function') {
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

onMounted(async () => {
  try {
    const cfg = (await req('get', '/config')) || {}
    form.value = { ...form.value, ...cfg }
  } catch (e) {
    message.value = describeError(e)
    messageType.value = 'error'
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  message.value = ''
  try {
    const payload = { ...form.value, run_once: form.value.run_once }
    const res = await req('post', '/config/save', payload)
    message.value = res?.message || '配置已保存'
    messageType.value = 'success'
    emit('action')
  } catch (e) {
    message.value = describeError(e)
    messageType.value = 'error'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <VContainer fluid class="pa-4">
    <div class="text-h6 mb-1">站点等级看板 · 配置</div>
    <div class="text-caption text-medium-emphasis mb-3">
      站点列表的增删在「数据」页(左侧列表 + 新增站点)。
    </div>

    <VProgressLinear v-if="loading" indeterminate color="primary" class="mb-3" />
    <VAlert v-if="message" :type="messageType" variant="tonal" density="compact" class="mb-3">{{ message }}</VAlert>

    <VCard variant="outlined" class="mb-3">
      <VCardTitle class="text-subtitle-2">① 通用</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow dense>
          <VCol cols="12" md="3"><VSwitch v-model="form.enabled" label="启用插件" hide-details /></VCol>
          <VCol cols="12" md="3"><VSwitch v-model="form.notify" label="启用通知" hide-details /></VCol>
          <VCol cols="12" md="3"><VSwitch v-model="form.notify_daily" label="每日汇总" hide-details /></VCol>
          <VCol cols="12" md="3"><VSwitch v-model="form.debug" label="详细日志" hide-details /></VCol>
        </VRow>
        <VRow dense class="mt-1">
          <VCol cols="12" md="4">
            <VTextField v-model="form.cron" label="刷新周期(cron)" placeholder="45 8 * * *" hide-details
                        density="compact" variant="outlined" persistent-hint
                        hint="默认每天 45 8 * * *,刻意避开其它插件的 08:00 / 08:30" />
          </VCol>
          <VCol cols="12" md="4">
            <VTextField v-model="form.notify_channel" label="通知渠道(留空=全部渠道)" density="compact"
                        variant="outlined" hide-details />
          </VCol>
          <VCol cols="12" md="2">
            <VTextField v-model="form.quiet_start" label="免打扰开始" placeholder="23:30" density="compact"
                        variant="outlined" hide-details />
          </VCol>
          <VCol cols="12" md="2">
            <VTextField v-model="form.quiet_end" label="免打扰结束" placeholder="07:00" density="compact"
                        variant="outlined" hide-details />
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard variant="outlined" class="mb-3">
      <VCardTitle class="text-subtitle-2">② 通知(三个开关可任意组合)</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow dense>
          <VCol cols="12" md="4"><VSwitch v-model="form.notify_level_change" label="等级变化时通知" hide-details /></VCol>
          <VCol cols="12" md="4"><VSwitch v-model="form.notify_risk" label="风险通知" hide-details /></VCol>
          <VCol cols="12" md="4"><VSwitch v-model="form.notify_eta" label="ETA 阈值通知" hide-details /></VCol>
        </VRow>
        <VRow v-if="form.notify_eta" dense class="mt-1">
          <VCol cols="12" md="4">
            <VTextField v-model.number="form.eta_threshold_days" type="number" label="ETA 阈值(天)"
                        density="compact" variant="outlined" hide-details />
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard variant="outlined" class="mb-3">
      <VCardTitle class="text-subtitle-2">③ 数据源</VCardTitle>
      <VDivider />
      <VCardText>
        <VRow dense>
          <VCol cols="12" md="6">
            <VSelect v-model="form.prefer_source" :items="[
              { title: '站点页优先(推荐)', value: 'site_page' },
              { title: '内置快照优先', value: 'snapshot' }]"
                     item-title="title" item-value="value" label="等级规则优先来源" density="compact"
                     variant="outlined" hide-details />
          </VCol>
          <VCol cols="12" md="3"><VSwitch v-model="form.use_site_page" label="允许抓站点页" hide-details /></VCol>
          <VCol cols="12" md="3">
            <VTextField v-model.number="form.timeout" type="number" label="请求超时(秒)" density="compact"
                        variant="outlined" hide-details />
          </VCol>
        </VRow>
      </VCardText>
    </VCard>

    <VCard variant="outlined" class="mb-3">
      <VCardTitle class="text-subtitle-2">④ 规则与兜底</VCardTitle>
      <VDivider />
      <VCardText>
        <VSwitch v-model="form.manual_first" label="手动规则优先于内置规则" hide-details class="mb-2" />
        <VTextarea v-model="form.manual_rules" label="手动等级规则(每行一条)" rows="4" density="compact"
                   variant="outlined" hide-details
                   placeholder="站点ID|等级名|条件表达式,如:2|Lv.4|经验>=20000" />
        <div class="text-caption text-medium-emphasis mt-2">
          站点不公开等级门槛时(如馒头)用内置快照兜底,数据页会标注来源与快照日期;有更准的门槛可填在这里覆盖。
        </div>
      </VCardText>
    </VCard>

    <div class="d-flex align-center">
      <VBtn color="primary" variant="flat" prepend-icon="mdi-content-save" :loading="saving" @click="save">
        保存配置
      </VBtn>
      <VSpacer />
      <span class="text-caption text-medium-emphasis">保存会重新初始化插件并刷新调度(等效插件列表里点保存)</span>
    </div>
  </VContainer>
</template>
