CLAIM_STATUSES = {"intake", "initial_review", "modeled", "investigating", "adjudicating", "closed", "rejected"}
RISK_LEVELS = {"low", "medium", "high"}
TASK_STATUSES = {"queued", "assigned", "in_progress", "completed", "cancelled"}
ROLES = {"intake_agent", "investigator", "risk_manager"}

CLUE_REVIEW_CLAIM_STATUSES = {"investigating", "adjudicating"}
CLUE_REVIEW_OPEN_STATUSES = ("pending", "returned")

# 付款单状态：reserved=占款中, paid=已实付, rejected=银行拒付（额度退回）, suspended=回执异常挂起
PAYMENT_ORDER_STATUSES = {"reserved", "paid", "rejected", "suspended"}
PAYMENT_FUND_STATUSES = ("reserved", "paid", "suspended")
PAYMENT_RECEIPT_RESULTS = {"confirmed", "rejected", "mismatch"}
# 核定与付款只允许在待核赔（含付款中）阶段操作，结案后冻结
PAYMENT_CLAIM_STATUSES = {"adjudicating"}
