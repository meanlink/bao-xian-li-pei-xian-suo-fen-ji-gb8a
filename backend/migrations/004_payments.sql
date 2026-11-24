-- 核赔付款模块：核定额、分笔付款单与银行回执
ALTER TABLE claims ADD COLUMN IF NOT EXISTS approved_amount NUMERIC(12,2);

-- 每案一条核定记录（1:1），核定金额即付款额度上限
CREATE TABLE IF NOT EXISTS payment_approvals (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
    approved_amount NUMERIC(12,2) NOT NULL CHECK (approved_amount > 0),
    note TEXT CHECK (note IS NULL OR char_length(btrim(note)) BETWEEN 2 AND 500),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 付款单：开出即占款（reserved）。paid=实付，rejected=明确拒付退回额度，suspended=回执异常挂起
CREATE TABLE IF NOT EXISTS payment_orders (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    order_no TEXT UNIQUE NOT NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    payee_name TEXT NOT NULL,
    payee_account TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    purpose TEXT NOT NULL CHECK (char_length(btrim(purpose)) BETWEEN 2 AND 300),
    status TEXT NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved','paid','rejected','suspended')),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    reject_reason TEXT CHECK (reject_reason IS NULL OR char_length(btrim(reject_reason)) BETWEEN 2 AND 500),
    rejected_by INTEGER REFERENCES users(id),
    suspended_at TIMESTAMPTZ,
    suspend_reason TEXT CHECK (suspend_reason IS NULL OR char_length(btrim(suspend_reason)) BETWEEN 2 AND 500),
    CHECK (status <> 'paid' OR paid_at IS NOT NULL),
    CHECK (status <> 'rejected' OR rejected_at IS NOT NULL),
    CHECK (status <> 'suspended' OR suspended_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS payment_orders_claim_idx ON payment_orders(claim_id, sequence_no);

-- 银行回执：同一回执单号全局唯一，重试提交不会产生第二条入账记录
CREATE TABLE IF NOT EXISTS payment_receipts (
    id SERIAL PRIMARY KEY,
    receipt_no TEXT UNIQUE NOT NULL CHECK (char_length(btrim(receipt_no)) BETWEEN 3 AND 64),
    order_id INTEGER NOT NULL REFERENCES payment_orders(id) ON DELETE CASCADE,
    received_amount NUMERIC(12,2) NOT NULL CHECK (received_amount > 0),
    result TEXT NOT NULL CHECK (result IN ('confirmed','rejected','mismatch')),
    note TEXT,
    recorded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS payment_receipts_order_idx ON payment_receipts(order_id, id);
