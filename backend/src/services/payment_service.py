from decimal import Decimal

import psycopg

from src.constants.enums import PAYMENT_CLAIM_STATUSES, PAYMENT_FUND_STATUSES
from src.utils.audit import record_in_transaction
from src.utils.db import get_conn


class PaymentError(ValueError):
    """业务校验失败，映射为 400。"""


class PaymentConflict(PermissionError):
    """状态冲突或越权，映射为 409。"""


class PaymentNotFound(LookupError):
    """资源不存在，映射为 404。"""


def _money(value):
    if value is None:
        return None
    return float(value)


def _order(row):
    if not row:
        return None
    item = dict(row)
    for key in ("amount", "received_amount"):
        if item.get(key) is not None:
            item[key] = _money(item[key])
    return item


def _lock_claim(conn, claim_id):
    """所有付款写操作先取案件行锁，串行化同一案件的额度变动，杜绝并发超额开单。"""
    claim = conn.execute(
        "SELECT id, claim_no, status, loss_amount, approved_amount FROM claims WHERE id=%s FOR UPDATE",
        (claim_id,),
    ).fetchone()
    if not claim:
        raise PaymentNotFound("案件不存在")
    if claim["status"] not in PAYMENT_CLAIM_STATUSES:
        raise PaymentConflict("仅待核赔阶段的案件可以进行核定与付款，案件当前不可操作")
    return claim


def _funds(conn, claim_id):
    """在已持有案件行锁的前提下汇总额度。reserved/suspended 继续占款，rejected 不占款。"""
    row = conn.execute(
        """
        SELECT COALESCE(sum(amount) FILTER (WHERE status = ANY(%(statuses)s)), 0) AS occupied,
               COALESCE(sum(amount) FILTER (WHERE status = 'paid'), 0) AS paid
        FROM payment_orders WHERE claim_id = %(claim)s
        """,
        {"statuses": list(PAYMENT_FUND_STATUSES), "claim": claim_id},
    ).fetchone()
    return Decimal(row["occupied"]), Decimal(row["paid"])


def get_payment_overview(claim_id):
    """案件页面的资金视图：核定、占款、实付、可开单额度与每笔款去向。"""
    with get_conn() as conn:
        claim = conn.execute(
            "SELECT id, claim_no, status, approved_amount FROM claims WHERE id=%s",
            (claim_id,),
        ).fetchone()
        if not claim:
            raise PaymentNotFound("案件不存在")
        approval = conn.execute(
            """SELECT a.*, u.display_name AS created_by_name
               FROM payment_approvals a JOIN users u ON u.id=a.created_by
               WHERE a.claim_id=%s""",
            (claim_id,),
        ).fetchone()
        orders = conn.execute(
            """SELECT o.*,
                      (SELECT count(*) FROM payment_receipts r WHERE r.order_id=o.id) AS receipt_count,
                      (SELECT r.receipt_no FROM payment_receipts r WHERE r.order_id=o.id ORDER BY r.id LIMIT 1) AS latest_receipt_no
               FROM payment_orders o WHERE o.claim_id=%s ORDER BY o.sequence_no, o.id""",
            (claim_id,),
        ).fetchall()
        receipts = conn.execute(
            """SELECT r.*, o.order_no, u.display_name AS recorded_by_name
               FROM payment_receipts r
               JOIN payment_orders o ON o.id=r.order_id
               JOIN users u ON u.id=r.recorded_by
               WHERE o.claim_id=%s ORDER BY r.id DESC""",
            (claim_id,),
        ).fetchall()

    approved = Decimal(claim["approved_amount"]) if claim["approved_amount"] is not None else Decimal("0")
    occupied = sum((Decimal(o["amount"]) for o in orders if o["status"] in PAYMENT_FUND_STATUSES), Decimal("0"))
    paid = sum((Decimal(o["amount"]) for o in orders if o["status"] == "paid"), Decimal("0"))
    available = approved - occupied
    result = {
        "claim_id": claim_id,
        "claim_no": claim["claim_no"],
        "claim_status": claim["status"],
        "approved_amount": _money(approved) if approved else None,
        "occupied_amount": _money(occupied),
        "paid_amount": _money(paid),
        "available_amount": _money(available),
        "fully_paid": approved > 0 and paid >= approved,
        "approval": dict(approval) if approval else None,
        "orders": [_order(o) for o in orders],
        "receipts": [_order(r) for r in receipts],
    }
    if result["approval"]:
        result["approval"]["approved_amount"] = _money(approval["approved_amount"])
    return result


def approve_payment(claim_id, payload, user_id):
    with get_conn() as conn:
        claim = _lock_claim(conn, claim_id)
        existing = conn.execute(
            "SELECT id, approved_amount FROM payment_approvals WHERE claim_id=%s FOR UPDATE",
            (claim_id,),
        ).fetchone()
        occupied, paid = _funds(conn, claim_id)
        amount = payload.approved_amount
        if existing:
            # 已有付款占用时，核定额不能低于已占款/实付，否则在途单据失去额度依据
            if amount < occupied:
                raise PaymentConflict(f"当前已占款 {occupied}，核定额不能下调到已占用额度之下")
            row = conn.execute(
                """UPDATE payment_approvals SET approved_amount=%s, note=%s, created_by=%s, updated_at=now()
                   WHERE claim_id=%s RETURNING *""",
                (amount, payload.note, user_id, claim_id),
            ).fetchone()
            action = "payment_approval_updated"
        else:
            if claim["loss_amount"] is not None and amount > Decimal(claim["loss_amount"]):
                raise PaymentError("核定金额不能超过报案损失金额")
            row = conn.execute(
                """INSERT INTO payment_approvals(claim_id, approved_amount, note, created_by)
                   VALUES (%s,%s,%s,%s) RETURNING *""",
                (claim_id, amount, payload.note, user_id),
            ).fetchone()
            action = "payment_approved"
        conn.execute(
            "UPDATE claims SET approved_amount=%s, updated_at=now() WHERE id=%s",
            (amount, claim_id),
        )
        record_in_transaction(conn, user_id, action, claim_id, {
            "approval_id": row["id"], "approved_amount": float(amount),
            "occupied_amount": float(occupied), "paid_amount": float(paid), "note": payload.note,
        })
        # 核定额下调到等于已实付、且无在途占款时，直接结案，避免案件卡死
        maybe_close(conn, claim, user_id)
    return _order(row) | {"approved_amount": _money(row["approved_amount"])}


def create_order(claim_id, payload, user_id):
    with get_conn() as conn:
        claim = _lock_claim(conn, claim_id)
        approval = conn.execute(
            "SELECT approved_amount FROM payment_approvals WHERE claim_id=%s",
            (claim_id,),
        ).fetchone()
        if not approval:
            raise PaymentConflict("本案尚未核定金额，不能开付款单")
        occupied, _paid = _funds(conn, claim_id)
        approved = Decimal(approval["approved_amount"])
        available = approved - occupied
        if payload.amount > available:
            raise PaymentConflict(
                f"可开单额度不足：核定 {approved}，已占款 {occupied}，剩余可开 {available}，本次申请 {payload.amount}"
            )
        sequence = conn.execute(
            "SELECT COALESCE(max(sequence_no),0)+1 AS next FROM payment_orders WHERE claim_id=%s",
            (claim_id,),
        ).fetchone()["next"]
        # 含案件唯一编号，保证不同案件的付款单号全局不撞号
        order_no = f"PAY-{claim['claim_no'].replace('CLM-', '')}-{sequence:03d}"
        row = conn.execute(
            """INSERT INTO payment_orders
                   (claim_id, order_no, sequence_no, payee_name, payee_account, bank_name, amount, purpose, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (claim_id, order_no, sequence, payload.payee_name, payload.payee_account,
             payload.bank_name, payload.amount, payload.purpose, user_id),
        ).fetchone()
        record_in_transaction(conn, user_id, "payment_order_created", claim_id, {
            "order_id": row["id"], "order_no": order_no, "sequence_no": sequence,
            "amount": float(payload.amount), "available_after": float(available - payload.amount),
        })
    return _order(row)


def _lock_order(conn, order_id):
    order = conn.execute("SELECT * FROM payment_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
    if not order:
        raise PaymentNotFound("付款单不存在")
    claim = _lock_claim(conn, order["claim_id"])
    return order, claim


def register_receipt(order_id, payload, user_id):
    """登记银行回执。重复回执号直接返回既有记录，不重复入账（接口幂等）。"""
    with get_conn() as conn:
        dup = conn.execute(
            """SELECT r.*, o.claim_id FROM payment_receipts r
               JOIN payment_orders o ON o.id=r.order_id WHERE r.receipt_no=%s""",
            (payload.receipt_no,),
        ).fetchone()
        if dup:
            if dup["order_id"] != order_id:
                raise PaymentConflict(
                    f"回执单号 {payload.receipt_no} 已用于付款单 {dup['order_id']}，不能重复登记"
                )
            # 同一付款单同一回执重试：原样返回，不产生新入账
            return {"idempotent": True, "receipt": _order(dup), "order": _order(
                conn.execute("SELECT * FROM payment_orders WHERE id=%s", (order_id,)).fetchone())}

        order, claim = _lock_order(conn, order_id)
        if order["status"] == "paid":
            raise PaymentConflict("付款单已确认实付，不能重复登记回执")
        if order["status"] == "rejected":
            raise PaymentConflict("付款单已拒付退回，不能再登记回执")

        try:
            receipt = conn.execute(
                """INSERT INTO payment_receipts(receipt_no, order_id, received_amount, result, note, recorded_by)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                (payload.receipt_no, order_id, payload.received_amount, payload.result, payload.note, user_id),
            ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            # 并发下另一事务刚写入相同回执号：不重复入账，交给调用方以冲突提示
            raise PaymentConflict(
                f"回执单号 {payload.receipt_no} 已存在，同一回执不能重复登记"
            ) from exc

        detail = {
            "order_id": order_id, "order_no": order["order_no"], "receipt_no": payload.receipt_no,
            "result": payload.result, "received_amount": float(payload.received_amount),
            "order_amount": float(order["amount"]),
        }
        order_amount = Decimal(order["amount"])
        received = payload.received_amount

        if payload.result == "confirmed" and received == order_amount:
            # 回执确认且金额一致：占款转实付
            row = conn.execute(
                """UPDATE payment_orders SET status='paid', paid_at=now()
                   WHERE id=%s RETURNING *""",
                (order_id,),
            ).fetchone()
            record_in_transaction(conn, user_id, "payment_confirmed", claim["id"], detail)
            maybe_close(conn, claim, user_id)
        elif payload.result == "rejected":
            # 银行明确拒付：退回可用额度（金额不参与拒付判断，以银行拒付结论为准）
            row = conn.execute(
                """UPDATE payment_orders SET status='rejected', rejected_at=now(),
                          reject_reason=%s, rejected_by=%s WHERE id=%s RETURNING *""",
                (payload.note or "银行拒付", user_id, order_id),
            ).fetchone()
            record_in_transaction(conn, user_id, "payment_rejected", claim["id"], detail)
        else:
            # 单号或金额对不上（含 confirmed 但金额不一致、显式 mismatch）：挂起，继续占款
            reason = payload.note or "回执单号或金额与付款单不符，挂起待人工处理"
            if payload.result == "confirmed" and received != order_amount:
                reason = f"回执金额 {received} 与付款单金额 {order_amount} 不一致，挂起待人工处理"
            row = conn.execute(
                """UPDATE payment_orders SET status='suspended', suspended_at=now(),
                          suspend_reason=%s WHERE id=%s RETURNING *""",
                (reason, order_id),
            ).fetchone()
            record_in_transaction(conn, user_id, "payment_suspended", claim["id"], {**detail, "reason": reason})
    return {"idempotent": False, "receipt": _order(receipt), "order": _order(row)}


def resolve_suspension(order_id, payload, user_id):
    """挂起单人工处理：确认实付（金额以原付款单为准）或拒付退回额度。"""
    with get_conn() as conn:
        order, claim = _lock_order(conn, order_id)
        if order["status"] != "suspended":
            raise PaymentConflict("只有挂起中的付款单可以人工处理")
        action = payload.get("action")
        if action == "confirm":
            row = conn.execute(
                "UPDATE payment_orders SET status='paid', paid_at=now(), suspend_reason=NULL WHERE id=%s RETURNING *",
                (order_id,),
            ).fetchone()
            record_in_transaction(conn, user_id, "payment_suspension_confirmed", claim["id"], {
                "order_id": order_id, "order_no": order["order_no"], "amount": float(order["amount"]),
            })
            maybe_close(conn, claim, user_id)
        elif action == "reject":
            reason = (payload.get("reason") or "人工核定挂起单拒付").strip()
            if not 2 <= len(reason) <= 500:
                raise PaymentError("处理说明长度需在 2 到 500 字之间")
            row = conn.execute(
                """UPDATE payment_orders SET status='rejected', rejected_at=now(),
                          rejected_by=%s, reject_reason=%s, suspend_reason=NULL WHERE id=%s RETURNING *""",
                (user_id, reason, order_id),
            ).fetchone()
            record_in_transaction(conn, user_id, "payment_suspension_rejected", claim["id"], {
                "order_id": order_id, "order_no": order["order_no"], "reason": reason,
            })
        else:
            raise PaymentError("处理方式必须是 confirm 或 reject")
    return _order(row)


def maybe_close(conn, claim, user_id):
    """实付累计满核定额，且没有占款中/挂起的付款单时，案件自动结案。"""
    occupied, paid = _funds(conn, claim["id"])
    approval = conn.execute(
        "SELECT approved_amount FROM payment_approvals WHERE claim_id=%s",
        (claim["id"],),
    ).fetchone()
    if not approval:
        return
    approved = Decimal(approval["approved_amount"])
    if paid >= approved and occupied == paid and paid > 0:
        conn.execute(
            "UPDATE claims SET status='closed', updated_at=now() WHERE id=%s AND status <> 'closed'",
            (claim["id"],),
        )
        record_in_transaction(conn, user_id, "claim_closed_by_payment", claim["id"], {
            "approved_amount": float(approved), "paid_amount": float(paid),
        })
