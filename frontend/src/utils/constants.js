export const claimStatus = {intake:'待初审',initial_review:'待模型',modeled:'已分级',investigating:'调查中',adjudicating:'待核赔',closed:'已结案',rejected:'已驳回'};
export const riskLevel = {low:'低风险',medium:'中风险',high:'高风险'};
export const roleLabel = {intake_agent:'案件受理员',investigator:'调查员',risk_manager:'风险主管'};
export function money(value){return `¥${Number(value || 0).toLocaleString('zh-CN',{maximumFractionDigits:0})}`}
export function dateText(value){return value ? String(value).slice(0,10) : '-'}
export function statusBadge(status){const map={intake:'badge-gray',initial_review:'badge-blue',modeled:'badge-amber',investigating:'badge-red',adjudicating:'badge-purple',closed:'badge-mint'};return map[status] || 'badge-gray'}
export function escapeHtml(text){return String(text ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}

export const clueStatus = {open:'待核查', confirmed:'已证实', dismissed:'已排除'};
export const clueReviewStatus = {unsubmitted:'未提交', pending:'待主管复核', returned:'待补正', resolved:'已复核'};
export const clueEvidenceSource = {official_record:'官方记录', original_media:'原始影像', issuer_confirmation:'出具方回函'};
export const clueReviewClaimStatuses = ['investigating', 'adjudicating'];

export function canTriage(role){return role === 'intake_agent' || role === 'risk_manager'}

export const paymentOrderStatus = {reserved:'占款中', paid:'已实付', rejected:'已拒付', suspended:'已挂起'};
export const paymentStatusBadge = {reserved:'badge-amber', paid:'badge-mint', rejected:'badge-gray', suspended:'badge-red'};
export const receiptResult = {confirmed:'确认到账', rejected:'银行拒付', mismatch:'信息不符'};
export function isManager(role){return role === 'risk_manager'}
export function money2(value){return `¥${Number(value || 0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}`}
