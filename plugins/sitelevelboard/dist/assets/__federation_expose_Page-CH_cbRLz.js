import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { f as fmtGb, S as SOURCE_LABEL, a as fmtNum, b as fmtEta, d as describeError, C as CONFIDENCE_LABEL, u as unwrapResponse } from './utils-CnnlG5Jx.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment,withModifiers:_withModifiers,normalizeClass:_normalizeClass,unref:_unref} = await importShared('vue');


const _hoisted_1 = { class: "text-caption text-medium-emphasis" };
const _hoisted_2 = {
  key: 0,
  class: "text-caption text-medium-emphasis font-weight-regular"
};
const _hoisted_3 = {
  key: 0,
  class: "text-warning"
};
const _hoisted_4 = {
  key: 1,
  class: "pa-3 text-caption text-medium-emphasis"
};
const _hoisted_5 = { class: "pa-3" };
const _hoisted_6 = { class: "d-flex align-center flex-wrap ga-2 mb-2" };
const _hoisted_7 = { class: "text-h6" };
const _hoisted_8 = { class: "text-caption text-medium-emphasis" };
const _hoisted_9 = { key: 0 };
const _hoisted_10 = { key: 0 };
const _hoisted_11 = { key: 0 };
const _hoisted_12 = { key: 1 };
const _hoisted_13 = { key: 2 };
const _hoisted_14 = { key: 0 };
const _hoisted_15 = {
  key: 0,
  class: "text-medium-emphasis"
};
const _hoisted_16 = {
  key: 0,
  class: "text-medium-emphasis"
};
const _hoisted_17 = { class: "mr-1" };
const _hoisted_18 = { key: 0 };
const _hoisted_19 = { key: 1 };
const _hoisted_20 = { class: "text-caption" };
const _hoisted_21 = {
  key: 0,
  class: "text-medium-emphasis"
};
const _hoisted_22 = { key: 1 };
const _hoisted_23 = {
  key: 2,
  class: "text-error"
};
const _hoisted_24 = { class: "text-caption" };
const _hoisted_25 = {
  key: 0,
  class: "mb-2"
};
const _hoisted_26 = ["viewBox"];
const _hoisted_27 = ["points"];
const _hoisted_28 = { class: "text-caption text-medium-emphasis" };
const _hoisted_29 = { class: "text-caption mb-2" };
const _hoisted_30 = {
  key: 0,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_31 = { class: "text-caption text-medium-emphasis ml-2" };

const {computed,onMounted,ref} = await importShared('vue');

const REL_BASE = 'plugin/SiteLevelBoard';

const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
},
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

/**
 * 站点等级看板 · 主界面(左侧站点列表 + 右侧等级详情)
 *
 * 宿主(MP)在渲染本组件时注入 ``api``(HTTP 客户端:get/post/put/delete);
 * 独立开发时没有 ``api``,自动退化为 fetch(带 cookie)。
 * 数据全部来自插件后端 11 个端点,契约见插件 __init__.py 顶部说明。
 */
const props = __props;

/**
 * ⚠️ 宿主(MP)注入的 ``api`` 客户端**自带前缀**:其 axios 实例 ``baseURL: 'api/v1/'``
 *    (见 MP 前端 bundles,「站点刷流」等插件同样按此约定调用)。
 *    所以传给它的必须是**相对 path** ``plugin/SiteLevelBoard/...``;
 *    若自己再叠一层 ``/api/v1`` 前缀,axios 会拼成 ``/api/v1/api/v1/...``
 *    → 前端报「Not Found」(2026-10-11 实际踩坑就是这个)。
 *    ``ABS_BASE`` 只在没有 ``api``(独立开发,退化为 fetch)时使用。
 */
const ABS_BASE = `/api/v1/${REL_BASE}`;

const loading = ref(true);
const busy = ref(false);
const error = ref('');
const snack = ref({ show: false, text: '', color: 'success' });

const tracked = ref([]);
const candidates = ref([]);
const meta = ref({ last_refresh: null, snapshot_date: null });
const selectedId = ref(0);
const detail = ref(null);
const detailLoading = ref(false);

const addOpen = ref(false);
const addSearch = ref('');
const addSelected = ref([]);
const confirmTarget = ref(null);

const filteredCandidates = computed(() => {
  const kw = addSearch.value.trim().toLowerCase();
  if (!kw) return candidates.value
  return candidates.value.filter(
    item => `${item.name} ${item.domain}`.toLowerCase().includes(kw),
  )
});

const current = computed(() => tracked.value.find(item => item.id === selectedId.value) || null);

function toast(text, color = 'success') {
  snack.value = { show: true, text, color };
}

async function req(method, path, body) {
  let raw;
  if (props.api && typeof props.api[method] === 'function') {
    // 走宿主 api:相对 path(宿主已带 api/v1 前缀),见上方 REL_BASE 注释
    raw = await props.api[method](REL_BASE + path, body);
  } else {
    const res = await fetch(ABS_BASE + path, {
      method: method.toUpperCase(),
      credentials: 'include',
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    raw = await res.json();
  }
  return unwrapResponse(raw)
}

async function loadSites(keepSelection = true) {
  loading.value = true;
  error.value = '';
  try {
    const data = await req('get', '/sites');
    tracked.value = data.tracked || [];
    candidates.value = data.candidates || [];
    meta.value = { last_refresh: data.last_refresh, snapshot_date: data.snapshot_date };
    const exists = tracked.value.some(item => item.id === selectedId.value);
    if (!keepSelection || !exists) {
      selectedId.value = tracked.value.length ? tracked.value[0].id : 0;
    }
    if (selectedId.value) await loadDetail(selectedId.value);
    else detail.value = null;
  } catch (e) {
    error.value = describeError(e);
  } finally {
    loading.value = false;
  }
}

async function loadDetail(siteId) {
  if (!siteId) return
  detailLoading.value = true;
  try {
    detail.value = await req('get', `/detail?site_id=${siteId}`);
  } catch (e) {
    detail.value = null;
    error.value = describeError(e);
  } finally {
    detailLoading.value = false;
  }
}

function selectSite(id) {
  if (selectedId.value === id) return
  selectedId.value = id;
  loadDetail(id);
}

async function refreshAll() {
  busy.value = true;
  try {
    await req('post', '/refresh', {});
    toast('已开始全量刷新,稍后自动更新列表', 'info');
    // 后台刷新约 10~60 秒;这里做一次延迟重取 + 允许手动再点
    setTimeout(() => loadSites(true), 12000);
    setTimeout(() => loadSites(true), 40000);
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

async function refreshOne() {
  const site = current.value;
  if (!site) return
  busy.value = true;
  try {
    const data = await req('post', '/refresh', { site_id: site.id });
    detail.value = data;
    await loadSites(true);
    toast('已刷新该站点', 'success');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

function openAdd() {
  addSearch.value = '';
  addSelected.value = [];
  addOpen.value = true;
}

async function submitAdd() {
  if (!addSelected.value.length) {
    toast('请先勾选要加入的站点', 'warning');
    return
  }
  busy.value = true;
  try {
    await req('post', '/track', { site_ids: addSelected.value });
    addOpen.value = false;
    await loadSites(true);
    toast(`已加入 ${addSelected.value.length} 个站点`, 'success');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

async function doRemove(site) {
  busy.value = true;
  try {
    await req('post', '/untrack', { site_id: site.id });
    confirmTarget.value = null;
    if (selectedId.value === site.id) {
      detail.value = null;
      selectedId.value = 0;
    }
    await loadSites(false);
    toast(`已把「${site.name}」移出看板(不影响 mp 站点管理)`, 'info');
  } catch (e) {
    toast(describeError(e), 'error');
  } finally {
    busy.value = false;
  }
}

/**
 * 左侧列表拖拽排序:用原生 HTML5 DnD,不引第三方库(vuedraggable 没在宿主 shared 里,
 * 自己打包一份不划算)。落点用 dragIndex/overIndex 标出插入线,松手后先本地生效、
 * 再 POST /reorder 落库;失败就把顺序回滚,避免界面与后端不一致。
 */
const dragIndex = ref(-1);
const overIndex = ref(-1);

function onDragStart(index, event) {
  dragIndex.value = index;
  overIndex.value = index;
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(tracked.value[index]?.id ?? ''));
  }
}

function onDragOver(index) {
  if (dragIndex.value >= 0) overIndex.value = index;
}

async function onDrop(index) {
  const from = dragIndex.value;
  dragIndex.value = -1;
  overIndex.value = -1;
  if (from < 0 || from === index) return
  const before = tracked.value.slice();
  const list = tracked.value.slice();
  const [moved] = list.splice(from, 1);
  list.splice(index, 0, moved);
  tracked.value = list;
  try {
    await req('post', '/reorder', { site_ids: list.map(x => x.id) });
  } catch (e) {
    tracked.value = before;
    toast(describeError(e), 'error');
  }
}

function onDragEnd() {
  dragIndex.value = -1;
  overIndex.value = -1;
}

/** 历史上传曲线(内联 SVG,不引第三方图表库)。 */
const spark = computed(() => {
  const hist = detail.value?.history || [];
  if (hist.length < 2) return null
  const vals = hist.map(h => Number(h.upload_gb) || 0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = Math.max(max - min, 1);
  const w = 100;
  const h = 28;
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / span) * h;
    return `${x.toFixed(2)},${y.toFixed(2)}`
  });
  return { points: pts.join(' '), min, max, w, h }
});

const timelineTrend = computed(() => {
  const hist = detail.value?.history || [];
  if (hist.length < 2) return ''
  const a = hist[0];
  const b = hist[hist.length - 1];
  const du = (Number(b.upload_gb) || 0) - (Number(a.upload_gb) || 0);
  const dd = (Number(b.download_gb) || 0) - (Number(a.download_gb) || 0);
  const days = Math.max(hist.length - 1, 1);
  return `${a.day} → ${b.day}:上传 ${du >= 0 ? '+' : ''}${fmtGb(du)},下载 ${dd >= 0 ? '+' : ''}${fmtGb(dd)}`
    + `(日均 ${du >= 0 ? '+' : ''}${(du / days).toFixed(2)} GB / ${(dd / days).toFixed(2)} GB)`
});

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

onMounted(() => loadSites(true));

return (_ctx, _cache) => {
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VChip = _resolveComponent("VChip");
  const _component_VListItemTitle = _resolveComponent("VListItemTitle");
  const _component_VListItemSubtitle = _resolveComponent("VListItemSubtitle");
  const _component_VListItem = _resolveComponent("VListItem");
  const _component_VList = _resolveComponent("VList");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VTable = _resolveComponent("VTable");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCheckboxBtn = _resolveComponent("VCheckboxBtn");
  const _component_VCardActions = _resolveComponent("VCardActions");
  const _component_VDialog = _resolveComponent("VDialog");
  const _component_VSnackbar = _resolveComponent("VSnackbar");
  const _component_VContainer = _resolveComponent("VContainer");

  return (_openBlock(), _createBlock(_component_VContainer, {
    fluid: "",
    class: "pa-4"
  }, {
    default: _withCtx(() => [
      _createVNode(_component_VRow, {
        dense: "",
        align: "center",
        class: "mb-2"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCol, { cols: "auto" }, {
            default: _withCtx(() => [
              _createVNode(_component_VIcon, {
                icon: "mdi-account-star-outline",
                color: "primary",
                size: "28"
              })
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, null, {
            default: _withCtx(() => [
              _cache[8] || (_cache[8] = _createElementVNode("div", { class: "text-h6" }, "站点等级看板", -1)),
              _createElementVNode("div", _hoisted_1, " 上次刷新:" + _toDisplayString(meta.value.last_refresh || '从未') + " · 内置等级规则快照:" + _toDisplayString(meta.value.snapshot_date || '-') + " · 看板站点 " + _toDisplayString(tracked.value.length) + " 个 ", 1)
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, { cols: "auto" }, {
            default: _withCtx(() => [
              _createVNode(_component_VBtn, {
                size: "small",
                variant: "tonal",
                "prepend-icon": "mdi-refresh",
                loading: busy.value,
                onClick: refreshAll
              }, {
                default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                  _createTextVNode(" 刷新全部 ", -1)
                ]))]),
                _: 1
              }, 8, ["loading"])
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      (error.value)
        ? (_openBlock(), _createBlock(_component_VAlert, {
            key: 0,
            type: "error",
            variant: "tonal",
            density: "compact",
            class: "mb-3",
            closable: "",
            "onClick:close": _cache[0] || (_cache[0] = $event => (error.value = ''))
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(error.value), 1)
            ]),
            _: 1
          }))
        : _createCommentVNode("", true),
      _createVNode(_component_VRow, null, {
        default: _withCtx(() => [
          _createVNode(_component_VCol, {
            cols: "12",
            md: "3"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_VCard, { variant: "outlined" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VIcon, {
                        icon: "mdi-server-network",
                        start: "",
                        size: "18",
                        color: "primary"
                      }),
                      _createTextVNode("站点(" + _toDisplayString(tracked.value.length) + ") ", 1),
                      _createVNode(_component_VSpacer),
                      (tracked.value.length > 1)
                        ? (_openBlock(), _createElementBlock("span", _hoisted_2, [
                            _createVNode(_component_VIcon, {
                              icon: "mdi-drag-vertical",
                              size: "14"
                            }),
                            _cache[10] || (_cache[10] = _createTextVNode("拖动排序 ", -1))
                          ]))
                        : _createCommentVNode("", true)
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VDivider),
                  (tracked.value.length)
                    ? (_openBlock(), _createBlock(_component_VList, {
                        key: 0,
                        density: "compact",
                        nav: "",
                        class: "py-0"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(tracked.value, (s, i) => {
                            return (_openBlock(), _createBlock(_component_VListItem, {
                              key: s.id,
                              active: s.id === selectedId.value,
                              color: "primary",
                              draggable: "true",
                              class: _normalizeClass([
                'slb-item',
                dragIndex.value === i ? 'slb-dragging' : '',
                overIndex.value === i && dragIndex.value >= 0 && dragIndex.value !== i
                  ? (dragIndex.value > i ? 'slb-drop-above' : 'slb-drop-below') : '',
              ]),
                              onClick: $event => (selectSite(s.id)),
                              onDragstart: $event => (onDragStart(i, $event)),
                              onDragover: _withModifiers($event => (onDragOver(i)), ["prevent"]),
                              onDrop: _withModifiers($event => (onDrop(i)), ["prevent","stop"]),
                              onDragend: onDragEnd
                            }, {
                              prepend: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-circle",
                                  size: "10",
                                  color: riskColor(s.risk)
                                }, null, 8, ["color"])
                              ]),
                              append: _withCtx(() => [
                                _createVNode(_component_VBtn, {
                                  icon: "mdi-delete-outline",
                                  size: "x-small",
                                  variant: "text",
                                  color: "error",
                                  title: "移出看板",
                                  onClick: _withModifiers($event => (confirmTarget.value = s), ["stop"])
                                }, null, 8, ["onClick"])
                              ]),
                              default: _withCtx(() => [
                                _createVNode(_component_VListItemTitle, { class: "text-body-2" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(s.name) + " ", 1),
                                    _createVNode(_component_VChip, {
                                      size: "x-small",
                                      variant: "tonal",
                                      class: "ml-1"
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(s.level || '?'), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode(_component_VListItemSubtitle, { class: "text-caption" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(s.domain) + " ", 1),
                                    (!s.evaluated)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_3, " · 未评估"))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1032, ["active", "class", "onClick", "onDragstart", "onDragover", "onDrop"]))
                          }), 128))
                        ]),
                        _: 1
                      }))
                    : (_openBlock(), _createElementBlock("div", _hoisted_4, " 还没有站点。点下方「新增站点」从你的 mp 站点里挑。 ")),
                  _createVNode(_component_VDivider),
                  _createElementVNode("div", _hoisted_5, [
                    _createVNode(_component_VBtn, {
                      block: "",
                      variant: "tonal",
                      "prepend-icon": "mdi-plus",
                      onClick: openAdd
                    }, {
                      default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
                        _createTextVNode("新增站点", -1)
                      ]))]),
                      _: 1
                    })
                  ])
                ]),
                _: 1
              }),
              _createVNode(_component_VCard, {
                variant: "outlined",
                class: "mt-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCardText, { class: "text-caption text-medium-emphasis" }, {
                    default: _withCtx(() => [
                      _cache[12] || (_cache[12] = _createTextVNode(" 圆点含义:", -1)),
                      _createVNode(_component_VIcon, {
                        icon: "mdi-circle",
                        size: "10",
                        color: "success"
                      }),
                      _cache[13] || (_cache[13] = _createTextVNode(" 正常 · ", -1)),
                      _createVNode(_component_VIcon, {
                        icon: "mdi-circle",
                        size: "10",
                        color: "warning"
                      }),
                      _cache[14] || (_cache[14] = _createTextVNode(" 有提示 · ", -1)),
                      _createVNode(_component_VIcon, {
                        icon: "mdi-circle",
                        size: "10",
                        color: "error"
                      }),
                      _cache[15] || (_cache[15] = _createTextVNode(" 有硬风险 ", -1))
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_VCol, {
            cols: "12",
            md: "9"
          }, {
            default: _withCtx(() => [
              (!selectedId.value)
                ? (_openBlock(), _createBlock(_component_VCard, {
                    key: 0,
                    variant: "outlined"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VCardText, { class: "text-medium-emphasis" }, {
                        default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                          _createTextVNode("从左侧选择一个站点,这里会显示它的等级统计。", -1)
                        ]))]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                    _createVNode(_component_VCard, {
                      variant: "outlined",
                      class: "mb-3"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VCardText, null, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_6, [
                              _createElementVNode("span", _hoisted_7, _toDisplayString(detail.value?.site_name || current.value?.name), 1),
                              _createVNode(_component_VChip, {
                                color: "primary",
                                variant: "tonal"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(detail.value?.level || '?'), 1)
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_VIcon, {
                                icon: "mdi-arrow-right",
                                size: "18"
                              }),
                              _createVNode(_component_VChip, { variant: "outlined" }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(detail.value?.next_level || '未知/已最高'), 1)
                                ]),
                                _: 1
                              }),
                              (detail.value)
                                ? (_openBlock(), _createBlock(_component_VChip, {
                                    key: 0,
                                    color: detail.value.manual_blocked ? 'warning' : 'success',
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(_toDisplayString(etaText(detail.value)), 1)
                                    ]),
                                    _: 1
                                  }, 8, ["color"]))
                                : _createCommentVNode("", true),
                              _createVNode(_component_VSpacer),
                              _createVNode(_component_VBtn, {
                                size: "x-small",
                                variant: "text",
                                "prepend-icon": "mdi-refresh",
                                loading: busy.value,
                                onClick: refreshOne
                              }, {
                                default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                                  _createTextVNode(" 刷新本站 ", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading"]),
                              (detail.value?.site_url)
                                ? (_openBlock(), _createBlock(_component_VBtn, {
                                    key: 1,
                                    size: "x-small",
                                    variant: "text",
                                    "prepend-icon": "mdi-open-in-new",
                                    href: detail.value.site_url,
                                    target: "_blank"
                                  }, {
                                    default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                                      _createTextVNode("打开站点", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["href"]))
                                : _createCommentVNode("", true)
                            ]),
                            (detail.value && detail.value.progress_pct !== null && detail.value.progress_pct !== undefined)
                              ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                                  key: 0,
                                  "model-value": detail.value.progress_pct,
                                  height: "10",
                                  rounded: "",
                                  color: "primary",
                                  class: "mb-2"
                                }, null, 8, ["model-value"]))
                              : _createCommentVNode("", true),
                            _createElementVNode("div", _hoisted_8, [
                              (detail.value)
                                ? (_openBlock(), _createElementBlock("span", _hoisted_9, [
                                    _createTextVNode(" 晋级进度按「最紧条件」计 " + _toDisplayString(detail.value.progress_pct ?? 0) + "% · 数据来源:" + _toDisplayString(_unref(SOURCE_LABEL)[detail.value.source] || detail.value.source || '-') + " ", 1),
                                    (detail.value.source === 'ptd_snapshot')
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_10, "(快照 " + _toDisplayString(detail.value.snapshot_date) + ")", 1))
                                      : _createCommentVNode("", true),
                                    _createTextVNode(" · siteuserdata 更新于 " + _toDisplayString(detail.value.l1_updated || '-'), 1)
                                  ]))
                                : _createCommentVNode("", true)
                            ])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    (detailLoading.value)
                      ? (_openBlock(), _createBlock(_component_VProgressLinear, {
                          key: 0,
                          indeterminate: "",
                          color: "primary",
                          class: "mb-3"
                        }))
                      : _createCommentVNode("", true),
                    (detail.value?.reqs?.length)
                      ? (_openBlock(), _createBlock(_component_VCard, {
                          key: 1,
                          variant: "outlined",
                          class: "mb-3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-checkbox-marked-circle-outline",
                                  start: "",
                                  size: "18",
                                  color: "primary"
                                }),
                                _createTextVNode(" 下一级条件(已达成 " + _toDisplayString(detail.value.reqs.filter(r => r.met).length) + " / " + _toDisplayString(detail.value.reqs.length) + ") ", 1)
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_VDivider),
                            _createVNode(_component_VTable, { density: "compact" }, {
                              default: _withCtx(() => [
                                _cache[19] || (_cache[19] = _createElementVNode("thead", null, [
                                  _createElementVNode("tr", null, [
                                    _createElementVNode("th", { style: {"width":"46px"} }, "状态"),
                                    _createElementVNode("th", null, "条件"),
                                    _createElementVNode("th", { style: {"width":"120px"} }, "目标"),
                                    _createElementVNode("th", { style: {"width":"120px"} }, "当前"),
                                    _createElementVNode("th", { style: {"width":"190px"} }, "增速 / 预计")
                                  ])
                                ], -1)),
                                _createElementVNode("tbody", null, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.reqs, (r) => {
                                    return (_openBlock(), _createElementBlock("tr", {
                                      key: r.key,
                                      class: _normalizeClass({ 'text-medium-emphasis': r.met })
                                    }, [
                                      _createElementVNode("td", null, [
                                        _createVNode(_component_VIcon, {
                                          icon: r.met ? 'mdi-check-circle' : 'mdi-close-circle',
                                          color: r.met ? 'success' : 'error',
                                          size: "18"
                                        }, null, 8, ["icon", "color"])
                                      ]),
                                      _createElementVNode("td", null, _toDisplayString(r.label), 1),
                                      _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(r.target)) + _toDisplayString(r.unit), 1),
                                      _createElementVNode("td", null, _toDisplayString(r.current === null ? '取不到' : _unref(fmtNum)(r.current) + r.unit), 1),
                                      _createElementVNode("td", null, [
                                        (r.met)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_11, "已达成"))
                                          : (r.eta_days !== null && r.eta_days !== undefined)
                                            ? (_openBlock(), _createElementBlock("span", _hoisted_12, _toDisplayString(r.rate_label || '') + " → " + _toDisplayString(_unref(fmtEta)(r.eta_days)), 1))
                                            : (_openBlock(), _createElementBlock("span", _hoisted_13, _toDisplayString(r.rate_label || (r.eta_kind === 'manual' ? '需人为推动' : '趋势不足')), 1))
                                      ])
                                    ], 2))
                                  }), 128))
                                ])
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : (detail.value && !detail.value.reqs?.length)
                        ? (_openBlock(), _createBlock(_component_VAlert, {
                            key: 2,
                            type: "info",
                            variant: "tonal",
                            density: "compact",
                            class: "mb-3"
                          }, {
                            default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                              _createTextVNode(" 该站没有可解析的晋级条件(站点未公开门槛,可在插件配置里用「手动规则」补),以下仍显示当前等级与保号信息。 ", -1)
                            ]))]),
                            _: 1
                          }))
                        : _createCommentVNode("", true),
                    _createVNode(_component_VRow, { class: "mb-1" }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VCol, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCard, {
                              variant: "outlined",
                              class: "h-100"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VIcon, {
                                      icon: "mdi-shield-check-outline",
                                      start: "",
                                      size: "18",
                                      color: "success"
                                    }),
                                    _cache[21] || (_cache[21] = _createTextVNode("保号状态与条件 ", -1))
                                  ]),
                                  _: 1
                                }),
                                _createVNode(_component_VDivider),
                                _createVNode(_component_VCardText, { class: "text-body-2" }, {
                                  default: _withCtx(() => [
                                    (detail.value)
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_14, [
                                          _createElementVNode("div", null, [
                                            _cache[22] || (_cache[22] = _createTextVNode("可封存保号(封存后不会被删):", -1)),
                                            _createElementVNode("b", null, _toDisplayString(detail.value.keep?.parkable_now ? '✅ 已达'
                      : (detail.value.keep?.levels_to_parkable !== null && detail.value.keep?.levels_to_parkable !== undefined
                        ? `还差 ${detail.value.keep.levels_to_parkable} 级` : '未知')), 1)
                                          ]),
                                          _createElementVNode("div", null, [
                                            _cache[23] || (_cache[23] = _createTextVNode("永久保留(不封存也不删):", -1)),
                                            _createElementVNode("b", null, _toDisplayString(detail.value.keep?.permanent_now ? '✅ 已达'
                      : (detail.value.keep?.levels_to_permanent !== null && detail.value.keep?.levels_to_permanent !== undefined
                        ? `还差 ${detail.value.keep.levels_to_permanent} 级` : '未知')), 1)
                                          ]),
                                          _createVNode(_component_VDivider, { class: "my-2" }),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.keep_rules || [], (t, i) => {
                                            return (_openBlock(), _createElementBlock("div", {
                                              key: 'k' + i
                                            }, "✅ " + _toDisplayString(t), 1))
                                          }), 128)),
                                          (!(detail.value.keep_rules || []).length)
                                            ? (_openBlock(), _createElementBlock("div", _hoisted_15, "站点未提供保号条款"))
                                            : _createCommentVNode("", true)
                                        ]))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VCol, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCard, {
                              variant: "outlined",
                              class: "h-100"
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VIcon, {
                                      icon: "mdi-alert-octagon-outline",
                                      start: "",
                                      size: "18",
                                      color: "error"
                                    }),
                                    _cache[24] || (_cache[24] = _createTextVNode("封号 / 降级条款 ", -1))
                                  ]),
                                  _: 1
                                }),
                                _createVNode(_component_VDivider),
                                _createVNode(_component_VCardText, { class: "text-body-2" }, {
                                  default: _withCtx(() => [
                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value?.ban_rules || [], (t, i) => {
                                      return (_openBlock(), _createElementBlock("div", {
                                        key: 'b' + i,
                                        class: "mb-1"
                                      }, "⛔ " + _toDisplayString(t), 1))
                                    }), 128)),
                                    (!detail.value?.ban_rules?.length)
                                      ? (_openBlock(), _createElementBlock("div", _hoisted_16, " 站点未提供(或不在公开页面)——请以站点公告为准 "))
                                      : _createCommentVNode("", true),
                                    (detail.value?.risks?.length)
                                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                          _createVNode(_component_VDivider, { class: "my-2" }),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.risks, (r, i) => {
                                            return (_openBlock(), _createElementBlock("div", {
                                              key: 'r' + i,
                                              class: _normalizeClass(r.level === 'danger' ? 'text-error' : 'text-warning')
                                            }, _toDisplayString(r.level === 'danger' ? '🔴' : '⚠️') + " " + _toDisplayString(r.text), 3))
                                          }), 128))
                                        ], 64))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    (detail.value?.ladder?.length)
                      ? (_openBlock(), _createBlock(_component_VCard, {
                          key: 3,
                          variant: "outlined",
                          class: "mt-3 mb-3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-stairs",
                                  start: "",
                                  size: "18",
                                  color: "primary"
                                }),
                                _cache[25] || (_cache[25] = _createTextVNode("全部等级阶梯 ", -1)),
                                _createVNode(_component_VSpacer),
                                _cache[26] || (_cache[26] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "🏅 永久保号 · 🔒 可封存保号", -1))
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_VDivider),
                            _createVNode(_component_VTable, { density: "compact" }, {
                              default: _withCtx(() => [
                                _cache[29] || (_cache[29] = _createElementVNode("thead", null, [
                                  _createElementVNode("tr", null, [
                                    _createElementVNode("th", { style: {"width":"150px"} }, "等级"),
                                    _createElementVNode("th", null, "晋级条件"),
                                    _createElementVNode("th", { style: {"width":"150px"} }, "特权 / 备注")
                                  ])
                                ], -1)),
                                _createElementVNode("tbody", null, [
                                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.ladder, (lv) => {
                                    return (_openBlock(), _createElementBlock("tr", {
                                      key: lv.order,
                                      class: _normalizeClass({ 'bg-primary': lv.order === detail.value.level_order, 'font-weight-bold': lv.order === detail.value.next_order })
                                    }, [
                                      _createElementVNode("td", null, [
                                        _createElementVNode("span", _hoisted_17, _toDisplayString(lv.order), 1),
                                        _createTextVNode(_toDisplayString(lv.name) + " ", 1),
                                        (lv.is_permanent)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_18, "🏅"))
                                          : _createCommentVNode("", true),
                                        (lv.is_parkable)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_19, "🔒"))
                                          : _createCommentVNode("", true),
                                        (lv.order === detail.value.level_order)
                                          ? (_openBlock(), _createBlock(_component_VChip, {
                                              key: 2,
                                              size: "x-small",
                                              color: "primary",
                                              class: "ml-1"
                                            }, {
                                              default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                                                _createTextVNode("当前", -1)
                                              ]))]),
                                              _: 1
                                            }))
                                          : (lv.order === detail.value.next_order)
                                            ? (_openBlock(), _createBlock(_component_VChip, {
                                                key: 3,
                                                size: "x-small",
                                                variant: "outlined",
                                                class: "ml-1"
                                              }, {
                                                default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                                                  _createTextVNode("下一级", -1)
                                                ]))]),
                                                _: 1
                                              }))
                                            : _createCommentVNode("", true)
                                      ]),
                                      _createElementVNode("td", _hoisted_20, [
                                        (!lv.requirements.length)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_21, "默认/无自动条件"))
                                          : (_openBlock(), _createElementBlock("span", _hoisted_22, _toDisplayString(lv.requirements.map(r => r.label).join(' · ')), 1)),
                                        (lv.demote_ratio)
                                          ? (_openBlock(), _createElementBlock("span", _hoisted_23, " (分享率 < " + _toDisplayString(lv.demote_ratio) + " 降级)", 1))
                                          : _createCommentVNode("", true)
                                      ]),
                                      _createElementVNode("td", _hoisted_24, _toDisplayString(lv.privilege || '-'), 1)
                                    ], 2))
                                  }), 128))
                                ])
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true),
                    (detail.value?.history?.length)
                      ? (_openBlock(), _createBlock(_component_VCard, {
                          key: 4,
                          variant: "outlined"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCardTitle, { class: "text-subtitle-2 d-flex align-center" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_VIcon, {
                                  icon: "mdi-chart-line",
                                  start: "",
                                  size: "18",
                                  color: "primary"
                                }),
                                _createTextVNode(" 流量时间线(最近 " + _toDisplayString(detail.value.history.length) + " 天 · 来自 mp 的 siteuserdata 日快照) ", 1)
                              ]),
                              _: 1
                            }),
                            _createVNode(_component_VDivider),
                            _createVNode(_component_VCardText, null, {
                              default: _withCtx(() => [
                                (spark.value)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_25, [
                                      (_openBlock(), _createElementBlock("svg", {
                                        viewBox: `0 0 ${spark.value.w} ${spark.value.h}`,
                                        preserveAspectRatio: "none",
                                        style: {"width":"100%","height":"56px"}
                                      }, [
                                        _createElementVNode("polyline", {
                                          points: spark.value.points,
                                          fill: "none",
                                          stroke: "rgb(var(--v-theme-primary))",
                                          "stroke-width": "1"
                                        }, null, 8, _hoisted_27)
                                      ], 8, _hoisted_26)),
                                      _createElementVNode("div", _hoisted_28, " 上传曲线(纵轴 " + _toDisplayString(_unref(fmtGb)(spark.value.min)) + " ~ " + _toDisplayString(_unref(fmtGb)(spark.value.max)) + ") ", 1)
                                    ]))
                                  : _createCommentVNode("", true),
                                _createElementVNode("div", _hoisted_29, _toDisplayString(timelineTrend.value), 1),
                                _createVNode(_component_VTable, { density: "compact" }, {
                                  default: _withCtx(() => [
                                    _cache[30] || (_cache[30] = _createElementVNode("thead", null, [
                                      _createElementVNode("tr", null, [
                                        _createElementVNode("th", null, "日期"),
                                        _createElementVNode("th", null, "上传"),
                                        _createElementVNode("th", null, "下载"),
                                        _createElementVNode("th", null, "分享率"),
                                        _createElementVNode("th", null, "魔力/积分"),
                                        _createElementVNode("th", null, "做种"),
                                        _createElementVNode("th", null, "做种体积")
                                      ])
                                    ], -1)),
                                    _createElementVNode("tbody", null, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(detail.value.history.slice(-14), (h) => {
                                        return (_openBlock(), _createElementBlock("tr", {
                                          key: h.day
                                        }, [
                                          _createElementVNode("td", null, _toDisplayString(h.day), 1),
                                          _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.upload_gb)), 1),
                                          _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.download_gb)), 1),
                                          _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(h.ratio, 3)), 1),
                                          _createElementVNode("td", null, _toDisplayString(_unref(fmtNum)(h.bonus, 1)), 1),
                                          _createElementVNode("td", null, _toDisplayString(h.seeding ?? '-'), 1),
                                          _createElementVNode("td", null, _toDisplayString(_unref(fmtGb)(h.seeding_size_gb)), 1)
                                        ]))
                                      }), 128))
                                    ])
                                  ]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true)
                  ], 64))
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VDialog, {
        modelValue: addOpen.value,
        "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((addOpen).value = $event)),
        "max-width": "640",
        scrollable: ""
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCard, null, {
            default: _withCtx(() => [
              _createVNode(_component_VCardTitle, { class: "text-subtitle-1 d-flex align-center" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VIcon, {
                    icon: "mdi-plus-circle-outline",
                    start: "",
                    color: "primary"
                  }),
                  _cache[31] || (_cache[31] = _createTextVNode("新增站点到看板 ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VDivider),
              _createVNode(_component_VCardText, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VTextField, {
                    modelValue: addSearch.value,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((addSearch).value = $event)),
                    density: "compact",
                    variant: "outlined",
                    "hide-details": "",
                    "prepend-inner-icon": "mdi-magnify",
                    label: "筛选站点(名称或域名)",
                    class: "mb-3"
                  }, null, 8, ["modelValue"]),
                  (!filteredCandidates.value.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_30, " 没有可添加的站点(要么都已在看板里,要么 mp 里还没绑定站点) "))
                    : (_openBlock(), _createBlock(_component_VList, {
                        key: 1,
                        density: "compact",
                        class: "py-0"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(filteredCandidates.value, (c) => {
                            return (_openBlock(), _createBlock(_component_VListItem, {
                              key: c.id,
                              onClick: $event => (addSelected.value.includes(c.id)
              ? (addSelected.value = addSelected.value.filter(x => x !== c.id))
              : addSelected.value.push(c.id))
                            }, {
                              prepend: _withCtx(() => [
                                _createVNode(_component_VCheckboxBtn, {
                                  "model-value": addSelected.value.includes(c.id),
                                  color: "primary"
                                }, null, 8, ["model-value"])
                              ]),
                              default: _withCtx(() => [
                                _createVNode(_component_VListItemTitle, { class: "text-body-2" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(c.name), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createVNode(_component_VListItemSubtitle, { class: "text-caption" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(c.domain), 1)
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1032, ["onClick"]))
                          }), 128))
                        ]),
                        _: 1
                      }))
                ]),
                _: 1
              }),
              _createVNode(_component_VDivider),
              _createVNode(_component_VCardActions, null, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_31, "已选 " + _toDisplayString(addSelected.value.length) + " 个", 1),
                  _createVNode(_component_VSpacer),
                  _createVNode(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[2] || (_cache[2] = $event => (addOpen.value = false))
                  }, {
                    default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                      _createTextVNode("取消", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_VBtn, {
                    color: "primary",
                    variant: "flat",
                    loading: busy.value,
                    onClick: submitAdd
                  }, {
                    default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                      _createTextVNode("加入看板", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["modelValue"]),
      _createVNode(_component_VDialog, {
        "model-value": !!confirmTarget.value,
        "max-width": "420",
        "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => (confirmTarget.value = null))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCard, null, {
            default: _withCtx(() => [
              _createVNode(_component_VCardTitle, { class: "text-subtitle-1" }, {
                default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
                  _createTextVNode("移出看板?", -1)
                ]))]),
                _: 1
              }),
              _createVNode(_component_VCardText, { class: "text-body-2" }, {
                default: _withCtx(() => [
                  _createTextVNode(" 将把「" + _toDisplayString(confirmTarget.value?.name) + "」从本站点看板里移除 —— ", 1),
                  _cache[35] || (_cache[35] = _createElementVNode("b", null, "不会", -1)),
                  _cache[36] || (_cache[36] = _createTextVNode("删除 mp 里的站点配置,之后还能再添加回来。 ", -1))
                ]),
                _: 1
              }),
              _createVNode(_component_VCardActions, null, {
                default: _withCtx(() => [
                  _createVNode(_component_VSpacer),
                  _createVNode(_component_VBtn, {
                    variant: "text",
                    onClick: _cache[4] || (_cache[4] = $event => (confirmTarget.value = null))
                  }, {
                    default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                      _createTextVNode("取消", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_VBtn, {
                    color: "error",
                    variant: "flat",
                    loading: busy.value,
                    onClick: _cache[5] || (_cache[5] = $event => (doRemove(confirmTarget.value)))
                  }, {
                    default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
                      _createTextVNode("移出", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading"])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }, 8, ["model-value"]),
      _createVNode(_component_VSnackbar, {
        modelValue: snack.value.show,
        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((snack.value.show) = $event)),
        color: snack.value.color,
        timeout: 3000,
        location: "bottom"
      }, {
        default: _withCtx(() => [
          _createTextVNode(_toDisplayString(snack.value.text), 1)
        ]),
        _: 1
      }, 8, ["modelValue", "color"])
    ]),
    _: 1
  }))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-334ab32d"]]);

export { Page as default };
