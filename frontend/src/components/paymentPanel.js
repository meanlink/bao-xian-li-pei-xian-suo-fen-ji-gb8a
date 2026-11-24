import {post} from '../api.js';
import {openModal, showToast} from './ui.js';
import {
  escapeHtml, isManager, money2, paymentOrderStatus, paymentStatusBadge, receiptResult,
} from '../utils/constants.js';

const canPay = user => isManager(user.role);
const dateTime = value => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '-';

function approvalModal(payment, claim, onSaved) {
  const current = payment.approval?.approved_amount;
  const modal = openModal(current ? '调整核定金额' : '核赔核定', `
    <form id="approvalForm" class="form-grid">
      <p class="notice full"><b>${escapeHtml(claim.claim_no)}</b> · 报案损失 ${money2(claim.loss_amount)}。
      核定金额是本案分笔付款的总额度，开单即占用额度。</p>
      <label class="field full">核定金额（元）
        <input name="approved_amount" type="number" step="0.01" min="0.01" max="${claim.loss_amount}"
               value="${current ?? claim.loss_amount}" required></label>
      <label class="field full">核定说明
        <textarea name="note" minlength="2" maxlength="500" placeholder="记录核定依据与赔付口径">${escapeHtml(payment.approval?.note ?? '')}</textarea></label>
      <p class="triage-error full" role="alert" hidden></p>
      <div class="full"><button class="btn btn-primary" type="submit">${current ? '保存调整' : '核定通过'}</button></div>
    </form>`);
  const form = modal.querySelector('#approvalForm');
  form.onsubmit = async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    body.approved_amount = Number(body.approved_amount);
    if (body.note && !body.note.trim()) body.note = null;
    const error = form.querySelector('[role=alert]');
    try {
      await post(`/claims/${claim.id}/payment-approval`, body);
      modal.remove();
      showToast('核定金额已保存');
      onSaved();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  };
}

function orderModal(payment, claim, onSaved) {
  const modal = openModal('开具付款单', `
    <form id="orderForm" class="form-grid">
      <p class="notice full">本案核定 ${money2(payment.approved_amount)}，已占款 ${money2(payment.occupied_amount)}，
      <b>还可开单 ${money2(payment.available_amount)}</b>。付款单开出即占款。</p>
      <label class="field">付款金额（元）
        <input name="amount" type="number" step="0.01" min="0.01" max="${payment.available_amount}"
               value="${Math.min(payment.available_amount, claim.loss_amount)}" required></label>
      <label class="field">收款银行
        <input name="bank_name" maxlength="60" value="工商银行城南支行" required></label>
      <label class="field">收款人
        <input name="payee_name" maxlength="80" value="${escapeHtml(claim.customer_name)}" required></label>
      <label class="field">收款账号
        <input name="payee_account" maxlength="40" placeholder="6222 0000 0000 0000" required></label>
      <label class="field full">付款用途
        <textarea name="purpose" minlength="2" maxlength="300" placeholder="例如：首笔车损维修款" required></textarea></label>
      <p class="triage-error full" role="alert" hidden></p>
      <div class="full"><button class="btn btn-primary" type="submit">开单并占款</button></div>
    </form>`);
  const form = modal.querySelector('#orderForm');
  form.onsubmit = async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    body.amount = Number(body.amount);
    const error = form.querySelector('[role=alert]');
    try {
      await post(`/claims/${claim.id}/payment-orders`, body);
      modal.remove();
      showToast('付款单已开出并占用额度');
      onSaved();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  };
}

function receiptModal(order, onSaved) {
  const modal = openModal(`登记银行回执 · ${order.order_no}`, `
    <form id="receiptForm" class="form-grid">
      <p class="notice full">付款单金额 <b>${money2(order.amount)}</b>，当前状态 ${paymentOrderStatus[order.status]}。
      回执单号或金额对不上将挂起单据并继续占款；同一回执重复提交不会重复入账。</p>
      <label class="field">银行回执单号
        <input name="receipt_no" minlength="3" maxlength="64" placeholder="例如 RCV-261106-003" required></label>
      <label class="field">回执结果
        <select name="result" required>
          <option value="confirmed">确认到账</option>
          <option value="rejected">银行拒付</option>
          <option value="mismatch">信息不符（挂起）</option>
        </select></label>
      <label class="field">回执金额（元）
        <input name="received_amount" type="number" step="0.01" min="0.01" value="${order.amount}" required></label>
      <label class="field full">备注
        <textarea name="note" minlength="2" maxlength="500" placeholder="记录银行反馈或差异说明"></textarea></label>
      <p class="triage-error full" role="alert" hidden></p>
      <div class="full"><button class="btn btn-primary" type="submit">提交回执</button></div>
    </form>`);
  const form = modal.querySelector('#receiptForm');
  form.onsubmit = async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    body.received_amount = Number(body.received_amount);
    if (body.note && !body.note.trim()) body.note = null;
    const error = form.querySelector('[role=alert]');
    try {
      const r = await post(`/payment-orders/${order.id}/receipts`, body);
      modal.remove();
      showToast(r.idempotent ? '该回执已登记，未重复入账' : '回执已处理');
      onSaved();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  };
}

function suspensionModal(order, onSaved) {
  const modal = openModal(`处理挂起单 · ${order.order_no}`, `
    <form id="suspensionForm" class="form-grid">
      <p class="notice danger full">挂起原因：${escapeHtml(order.suspend_reason || '回执单号或金额与付款单不符')}</p>
      <label class="field full">处理方式
        <select name="action" required>
          <option value="confirm">人工确认实付（按原付款单金额转实付）</option>
          <option value="reject">拒付退单（退回可用额度）</option>
        </select></label>
      <label class="field full">处理说明
        <textarea name="reason" minlength="2" maxlength="500" placeholder="记录人工核定依据" required></textarea></label>
      <p class="triage-error full" role="alert" hidden></p>
      <div class="full"><button class="btn btn-primary" type="submit">提交处理</button></div>
    </form>`);
  const form = modal.querySelector('#suspensionForm');
  form.onsubmit = async event => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    const error = form.querySelector('[role=alert]');
    try {
      await post(`/payment-orders/${order.id}/suspension`, body);
      modal.remove();
      showToast(body.action === 'confirm' ? '挂起单已转实付' : '挂起单已拒付，额度退回');
      onSaved();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  };
}

function orderRow(order, user, onSaved) {
  const actions = [];
  if (canPay(user) && ['reserved', 'suspended'].includes(order.status)) {
    actions.push(`<button class="btn btn-soft" data-receipt="${order.id}">登记回执</button>`);
  }
  if (canPay(user) && order.status === 'suspended') {
    actions.push(`<button class="btn btn-danger" data-suspension="${order.id}">人工处理</button>`);
  }
  const sub = [];
  if (order.paid_at) sub.push(`实付 ${dateTime(order.paid_at)}`);
  if (order.rejected_at) sub.push(`拒付 ${dateTime(order.rejected_at)}：${escapeHtml(order.reject_reason || '')}`);
  if (order.suspended_at) sub.push(`挂起 ${dateTime(order.suspended_at)}：${escapeHtml(order.suspend_reason || '')}`);
  if (order.latest_receipt_no) sub.push(`最近回执 ${escapeHtml(order.latest_receipt_no)}（共 ${order.receipt_count} 条）`);
  return `<tr>
    <td><div class="claim-id">${escapeHtml(order.order_no)}</div><div class="subline">第 ${order.sequence_no} 笔</div></td>
    <td><b>${money2(order.amount)}</b></td>
    <td><span class="badge ${paymentStatusBadge[order.status]}">${paymentOrderStatus[order.status]}</span></td>
    <td><b>${escapeHtml(order.payee_name)}</b><div class="subline">${escapeHtml(order.bank_name)} · ${escapeHtml(order.payee_account)}</div></td>
    <td>${escapeHtml(order.purpose)}<div class="subline">${sub.join(' · ') || '等待银行回执'}</div></td>
    <td><div class="review-actions">${actions.join('')}</div></td>
  </tr>`;
}

export function renderPaymentPanel(user, claim, payment, onSaved) {
  if (!payment) return '';
  const manager = canPay(user);
  const editable = manager && claim.status === 'adjudicating';
  const headActions = [];
  if (editable) {
    headActions.push(`<button class="btn btn-line" data-approval="1">${payment.approval ? '调整核定' : '核赔核定'}</button>`);
    if (payment.approval && payment.available_amount > 0) {
      headActions.push('<button class="btn btn-primary" data-new-order="1">+ 开付款单</button>');
    }
  }
  const frozen = claim.status === 'closed';
  const summary = payment.approval ? `
    <div class="grid grid-4 payment-summary">
      <div class="kv-item"><small>核定金额</small><b>${money2(payment.approved_amount)}</b></div>
      <div class="kv-item"><small>已实付</small><b style="color:var(--mint)">${money2(payment.paid_amount)}</b></div>
      <div class="kv-item"><small>占款中（含挂起）</small><b style="color:var(--amber)">${money2(payment.occupied_amount - payment.paid_amount)}</b></div>
      <div class="kv-item"><small>还可开单</small><b style="color:var(--blue)">${money2(payment.available_amount)}</b></div>
    </div>
    <div class="progress" style="margin:14px 0 4px"><span style="width:${Math.min(100, Math.round(payment.occupied_amount / payment.approved_amount * 100))}%"></span></div>
    <div class="subline">实付进度 ${Math.round(payment.paid_amount / payment.approved_amount * 100)}% ·
      实付满核定额且无占款/挂起单时自动结案</div>`
    : '<div class="empty">本案尚未核定金额。核赔通过后由风险主管登记核定金额，才能分笔开单。</div>';
  const rows = payment.orders.map(o => orderRow(o, user, onSaved)).join('');
  const receipts = payment.receipts.length ? payment.receipts.map(r => `
    <div class="triage-receipt" style="padding:10px 0;border-bottom:1px solid var(--line)">
      <div class="split"><b>${escapeHtml(r.receipt_no)}</b>
        <span class="badge ${r.result === 'confirmed' ? 'badge-mint' : r.result === 'rejected' ? 'badge-gray' : 'badge-red'}">${receiptResult[r.result]}</span></div>
      <div class="subline">${escapeHtml(r.order_no)} · 回执金额 ${money2(r.received_amount)} · ${escapeHtml(r.recorded_by_name)} · ${dateTime(r.created_at)}${r.note ? ' · ' + escapeHtml(r.note) : ''}</div>
    </div>`).join('') : '<p class="subline">暂无银行回执。</p>';
  const body = `
    ${summary}
    ${frozen ? '<div class="notice" style="margin-top:14px">案件已结案，付款额度冻结，仅可查看每笔款去向。</div>' : ''}
    <div class="table-wrap" style="margin-top:16px">
      <table class="table"><thead><tr><th>付款单</th><th>金额</th><th>状态</th><th>收款方</th><th>去向与回执</th><th>操作</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="empty">尚未开具付款单</td></tr>'}</tbody></table>
    </div>
    <h3 style="font-size:14px;margin:18px 0 6px">银行回执流水</h3>${receipts}`;
  const panel = `<section class="card section" id="paymentPanel">
    <div class="section-head"><div class="section-title">核赔付款 · 分笔占款</div><div class="review-actions">${headActions.join('')}</div></div>${body}</section>`;
  setTimeout(() => {
    document.querySelector('[data-approval]')?.addEventListener('click', () => approvalModal(payment, claim, onSaved));
    document.querySelector('[data-new-order]')?.addEventListener('click', () => orderModal(payment, claim, onSaved));
    document.querySelectorAll('[data-receipt]').forEach(btn => btn.addEventListener('click', () => {
      const order = payment.orders.find(o => o.id === Number(btn.dataset.receipt));
      receiptModal(order, onSaved);
    }));
    document.querySelectorAll('[data-suspension]').forEach(btn => btn.addEventListener('click', () => {
      const order = payment.orders.find(o => o.id === Number(btn.dataset.suspension));
      suspensionModal(order, onSaved);
    }));
  }, 0);
  return panel;
}
