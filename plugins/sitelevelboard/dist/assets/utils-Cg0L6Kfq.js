/**
 * 通用工具:响应解包 + 展示格式化。
 *
 * 后端(SiteLevelBoard 插件)统一返回 ``{success, message, data}``;
 * 与「站点刷流」插件的 unwrapResponse 保持同一约定,失败即抛错由调用方提示。
 */
function unwrapResponse(response) {
  if (response && Object.prototype.hasOwnProperty.call(response, 'success')) {
    if (response.success === false) throw new Error(response.message || '操作失败')
    return response.data
  }
  return response?.data ?? response
}

/**
 * 把请求错误转成一句人话。
 *
 * axios 对 4xx/5xx 是抛错而不是返回响应体,直接取 ``error.message`` 只能看到
 * 「Request failed with status code 404」;这里优先透出后端 ``{success,message}`` 里的 message。
 */
function describeError(error) {
  const body = error?.response?.data;
  if (body && typeof body === 'object' && body.message) return body.message
  return error?.message || String(error)
}

/** 预计天数 → 人类可读(0 天=已达成)。 */
function fmtEta(days) {
  if (days === null || days === undefined) return '无法估算'
  if (days <= 0) return '已达成'
  if (days < 1) return '<1 天'
  if (days > 365) return '>1 年'
  return `~${Math.round(days)} 天`
}

const CONFIDENCE_LABEL = { high: '高', mid: '中', low: '低', none: '不足' };

const SOURCE_LABEL = {
  site_page_verified: '站点页(已校验)',
  site_page_diff: '站点页(与快照不一致)',
  ptd_snapshot: '内置快照',
  depiler_snapshot: '规则库(depiler)',
  manual: '手动规则',
  l1_only: '仅当前等级',
  error: '评估失败',
};

/**
 * 等级名的匹配强度。exact 之外都要显式标出来:
 * 「靠别名猜的档位」和「原文一致的档位」可信度不一样,混在一起看会把猜的当成的。
 */
const LEVEL_MATCH_LABEL = {
  exact: '原文一致',
  compact: '空格差异',
  alias: '别名匹配',
  user_alias: '自定义别名',
  ambiguous: '别名歧义',
  off_ladder: '不在阶梯内',
  none: '未识别',
  empty: '站点未给等级',
};

/** 需要让人复核的匹配方式(不是原文一致,就不能装作一样可信)。 */
function isSoftMatch(how) {
  return how === 'alias' || how === 'compact' || how === 'user_alias'
}

function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v)
  if (Math.abs(n) >= 1000) return n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  return String(Number(n.toFixed(digits)))
}

function fmtGb(v) {
  if (v === null || v === undefined) return '-'
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v)
  if (n >= 1024) return `${(n / 1024).toFixed(2)} TB`
  return `${n.toFixed(n < 10 ? 2 : 1)} GB`
}

export { CONFIDENCE_LABEL as C, LEVEL_MATCH_LABEL as L, SOURCE_LABEL as S, fmtEta as a, fmtGb as b, describeError as d, fmtNum as f, isSoftMatch as i, unwrapResponse as u };
