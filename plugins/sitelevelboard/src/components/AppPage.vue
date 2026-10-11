<script setup>
/**
 * 独立运行入口(仅开发/构建用):MP 运行时加载的是 Page.vue,
 * 这里只是让 `vite dev` / 打包入口有个挂载点。
 */
import Page from './Page.vue'

defineProps({
  api: { type: Object, default: () => ({}) },
})
</script>

<template>
  <Page :api="api" />
</template>
