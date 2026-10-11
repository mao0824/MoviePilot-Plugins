import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import { d as describeError, u as unwrapResponse } from './utils-JdTrmUsi.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createVNode:_createVNode} = await importShared('vue');


const _hoisted_1 = { class: "d-flex align-center" };

const {onMounted,ref} = await importShared('vue');

const REL_BASE = 'plugin/SiteLevelBoard';

const _sfc_main = {
  __name: 'Config',
  props: {
  api: { type: Object, default: () => ({}) },
},
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

/**
 * 站点等级看板 · 配置页(Vue 版)
 *
 * 与声明式 ``get_form`` 共用同一份配置(后端 `/config`、`/config/save`),
 * 保存会走 MP 的 PluginConfigCommand.update(保存 + 重新初始化 + 刷新调度)。
 */
const props = __props;
const emit = __emit;

// 宿主 api 客户端自带 `api/v1/` 前缀 → 只能传相对 path(详见 Page.vue 顶部注释);
// ABS_BASE 仅供独立开发(无 api prop,退化为 fetch)使用。
const ABS_BASE = `/api/v1/${REL_BASE}`;
const saving = ref(false);
const loading = ref(true);
const message = ref('');
const messageType = ref('success');

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
});

async function req(method, path, body) {
  let raw;
  if (props.api && typeof props.api[method] === 'function') {
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

onMounted(async () => {
  try {
    const cfg = (await req('get', '/config')) || {};
    form.value = { ...form.value, ...cfg };
  } catch (e) {
    message.value = describeError(e);
    messageType.value = 'error';
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  message.value = '';
  try {
    const payload = { ...form.value, run_once: form.value.run_once };
    const res = await req('post', '/config/save', payload);
    message.value = res?.message || '配置已保存';
    messageType.value = 'success';
    emit('action');
  } catch (e) {
    message.value = describeError(e);
    messageType.value = 'error';
  } finally {
    saving.value = false;
  }
}

return (_ctx, _cache) => {
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VSelect = _resolveComponent("VSelect");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VContainer = _resolveComponent("VContainer");

  return (_openBlock(), _createBlock(_component_VContainer, {
    fluid: "",
    class: "pa-4"
  }, {
    default: _withCtx(() => [
      _cache[24] || (_cache[24] = _createElementVNode("div", { class: "text-h6 mb-1" }, "站点等级看板 · 配置", -1)),
      _cache[25] || (_cache[25] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mb-3" }, " 站点列表的增删在「数据」页(左侧列表 + 新增站点)。 ", -1)),
      (loading.value)
        ? (_openBlock(), _createBlock(_component_VProgressLinear, {
            key: 0,
            indeterminate: "",
            color: "primary",
            class: "mb-3"
          }))
        : _createCommentVNode("", true),
      (message.value)
        ? (_openBlock(), _createBlock(_component_VAlert, {
            key: 1,
            type: messageType.value,
            variant: "tonal",
            density: "compact",
            class: "mb-3"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(message.value), 1)
            ]),
            _: 1
          }, 8, ["type"]))
        : _createCommentVNode("", true),
      _createVNode(_component_VCard, {
        variant: "outlined",
        class: "mb-3"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "text-subtitle-2" }, {
            default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
              _createTextVNode("① 通用", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _createVNode(_component_VRow, { dense: "" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.enabled,
                        "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((form.value.enabled) = $event)),
                        label: "启用插件",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.notify,
                        "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((form.value.notify) = $event)),
                        label: "启用通知",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.notify_daily,
                        "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((form.value.notify_daily) = $event)),
                        label: "每日汇总",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.debug,
                        "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((form.value.debug) = $event)),
                        label: "详细日志",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              _createVNode(_component_VRow, {
                dense: "",
                class: "mt-1"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTextField, {
                        modelValue: form.value.cron,
                        "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((form.value.cron) = $event)),
                        label: "刷新周期(cron)",
                        placeholder: "45 8 * * *",
                        "hide-details": "",
                        density: "compact",
                        variant: "outlined",
                        "persistent-hint": "",
                        hint: "默认每天 45 8 * * *,刻意避开其它插件的 08:00 / 08:30"
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTextField, {
                        modelValue: form.value.notify_channel,
                        "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((form.value.notify_channel) = $event)),
                        label: "通知渠道(留空=全部渠道)",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "2"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTextField, {
                        modelValue: form.value.quiet_start,
                        "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((form.value.quiet_start) = $event)),
                        label: "免打扰开始",
                        placeholder: "23:30",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "2"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTextField, {
                        modelValue: form.value.quiet_end,
                        "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((form.value.quiet_end) = $event)),
                        label: "免打扰结束",
                        placeholder: "07:00",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
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
      _createVNode(_component_VCard, {
        variant: "outlined",
        class: "mb-3"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "text-subtitle-2" }, {
            default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
              _createTextVNode("② 通知(三个开关可任意组合)", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _createVNode(_component_VRow, { dense: "" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.notify_level_change,
                        "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((form.value.notify_level_change) = $event)),
                        label: "等级变化时通知",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.notify_risk,
                        "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((form.value.notify_risk) = $event)),
                        label: "风险通知",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.notify_eta,
                        "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((form.value.notify_eta) = $event)),
                        label: "ETA 阈值通知",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }),
              (form.value.notify_eta)
                ? (_openBlock(), _createBlock(_component_VRow, {
                    key: 0,
                    dense: "",
                    class: "mt-1"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VCol, {
                        cols: "12",
                        md: "4"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_VTextField, {
                            modelValue: form.value.eta_threshold_days,
                            "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((form.value.eta_threshold_days) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            label: "ETA 阈值(天)",
                            density: "compact",
                            variant: "outlined",
                            "hide-details": ""
                          }, null, 8, ["modelValue"])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }))
                : _createCommentVNode("", true)
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        variant: "outlined",
        class: "mb-3"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "text-subtitle-2" }, {
            default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
              _createTextVNode("③ 数据源", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _createVNode(_component_VRow, { dense: "" }, {
                default: _withCtx(() => [
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "6"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSelect, {
                        modelValue: form.value.prefer_source,
                        "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((form.value.prefer_source) = $event)),
                        items: [
              { title: '站点页优先(推荐)', value: 'site_page' },
              { title: '内置快照优先', value: 'snapshot' }],
                        "item-title": "title",
                        "item-value": "value",
                        label: "等级规则优先来源",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VSwitch, {
                        modelValue: form.value.use_site_page,
                        "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((form.value.use_site_page) = $event)),
                        label: "允许抓站点页",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_VCol, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VTextField, {
                        modelValue: form.value.timeout,
                        "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((form.value.timeout) = $event)),
                        modelModifiers: { number: true },
                        type: "number",
                        label: "请求超时(秒)",
                        density: "compact",
                        variant: "outlined",
                        "hide-details": ""
                      }, null, 8, ["modelValue"])
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
      _createVNode(_component_VCard, {
        variant: "outlined",
        class: "mb-3"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardTitle, { class: "text-subtitle-2" }, {
            default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
              _createTextVNode("④ 规则与兜底", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_VDivider),
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _createVNode(_component_VSwitch, {
                modelValue: form.value.manual_first,
                "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((form.value.manual_first) = $event)),
                label: "手动规则优先于内置规则",
                "hide-details": "",
                class: "mb-2"
              }, null, 8, ["modelValue"]),
              _createVNode(_component_VTextarea, {
                modelValue: form.value.manual_rules,
                "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((form.value.manual_rules) = $event)),
                label: "手动等级规则(每行一条)",
                rows: "4",
                density: "compact",
                variant: "outlined",
                "hide-details": "",
                placeholder: "站点ID|等级名|条件表达式,如:2|Lv.4|经验>=20000"
              }, null, 8, ["modelValue"]),
              _cache[21] || (_cache[21] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mt-2" }, " 站点不公开等级门槛时(如馒头)用内置快照兜底,数据页会标注来源与快照日期;有更准的门槛可填在这里覆盖。 ", -1))
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createElementVNode("div", _hoisted_1, [
        _createVNode(_component_VBtn, {
          color: "primary",
          variant: "flat",
          "prepend-icon": "mdi-content-save",
          loading: saving.value,
          onClick: save
        }, {
          default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
            _createTextVNode(" 保存配置 ", -1)
          ]))]),
          _: 1
        }, 8, ["loading"]),
        _createVNode(_component_VSpacer),
        _cache[23] || (_cache[23] = _createElementVNode("span", { class: "text-caption text-medium-emphasis" }, "保存会重新初始化插件并刷新调度(等效插件列表里点保存)", -1))
      ])
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
