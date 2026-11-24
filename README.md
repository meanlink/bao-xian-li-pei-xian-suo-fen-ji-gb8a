# 保险理赔线索分级

面向华东安心保险理赔中心的小型理赔线索分级工作台。它把报案受理、缺项补件、资料核验、风险分级和调查派单串在同一条理赔作业链上。

## 启动

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python scripts/seed_demo.py
```

访问 `http://localhost:18244`。演示账号统一密码为 `demo123`。

| 账号 | 角色 | 主要动作 |
|---|---|---|
| intake@claims.local | 案件受理员 | 新建案件、登记补件联系、核验资料 |
| investigator@claims.local | 调查员 | 查看线索、完成调查、提交和补正核验证据 |
| manager@claims.local | 风险主管 | 跟进逾期补件、模型分级、阈值评估回滚、主管复核、核赔结案 |

## 业务链

报案 → 初审 → 模型分级 → 调查 → 核赔。资料不完整的案件不能进入模型。阈值评估若误报率超过 25%，系统恢复上一个可用阈值并记录审计日志。

## 补件调度

受理员登录后打开「补件调度」。演示案件 `CLM-261102-0002` 缺少损失清单，尚未登记补件联系。登记沟通渠道、联系日期、约定补件期限与沟通结果。调度队列使用北京时间，把逾期、今日到期、待首次联系和等待补件的案件依次排开。同一组先处理期限更早的案件，期限相同则先处理损失金额较高的案件。

从队列进入「资料核验」勾选每件已经收到的材料。只收到一部分时，剩余缺项仍留在原期限，风险分级继续被阻断。全部核齐时，资料核验与补件回执在同一事务保存，案件退出补件队列并可由主管分级。在分级前纠正误勾的资料会重新进入队列，之前的回执保留。已经分级或进入后续流程的案件禁止将资料改回缺项。

补件联系记录仅向受理员和风险主管开放。重复登记、过时的联系版本和过时的缺项清单会收到冲突提示。该工作台登记已发生的联系，实际电话、短信与邮件由经办人在线下完成。

## 线索证据复核

试用案件 `CLM-261105-0005` 的「出险时间异常」线索。调查员在「证据复核」填写凭证类型、可追溯的编号、核验发现和证实或排除建议。风险主管可采纳建议并更新线索状态，也可注明缺项后退回补正。原调查员提交补正时进入下一轮，历史材料和每轮决定写入审计。受理员可查看进度。

仅调查中或待核赔案件的待核查线索可提交证据。已提交但待复核或待补正的记录会阻止核赔结案，案件详情显示对应数量和入口。主管决定会更新线索状态，历史模型分数保留原值。

后端启动时幂等创建复核表、补件跟进表与付款表（迁移 `002`–`004`），已有数据库卷可直接升级。重复运行演示 seed 会保留已经处理的理赔案件、线索、复核记录与付款单据。

## 核赔付款

核赔通过后，风险主管在待核赔案件上登记**核定金额**，作为本案分笔付款的总额度上限。核定金额不能超过报案损失金额；已有付款占用时，核定额不能下调到已占用额度之下。

- **开单即占款**：每张付款单开出立即占用额度。所有额度校验在单事务内对案件行加锁（`SELECT … FOR UPDATE`），并发开单串行化，任何一笔都不会使累计占款超出核定额。
- **回执驱动状态**：银行回执未到前单据保持「占款中」；回执确认且金额一致转「已实付」；银行明确拒付转「已拒付」并退回可用额度，可重新开单。
- **异常挂起**：回执单号或金额与付款单对不上时单据「已挂起」，继续占款，由主管人工确认实付或拒付退单。
- **回执幂等**：回执单号全局唯一。同一回执重复提交直接返回既有记录，不产生第二次入账；回执号跨付款单复用会被拒绝。
- **自动结案**：实付累计等于核定额、且没有占款中或挂起的单据时案件自动结案。已核定的案件不能再走手动结案，必须实付满额；未核定的零赔付案件仍可手动结案。结案后全部付款操作冻结。
- 案件详情页「核赔付款」面板展示核定、已实付、占款中（含挂起）、还可开单金额，以及每笔付款单的收款方、状态、去向和全部银行回执流水。

演示案件 `CLM-261106-0006` 已核定 10 万元，含一笔已实付和一笔占款中付款单，可直接练习回执登记、挂起处理与自动结案。

## 共享枚举

- 案件状态：`intake / initial_review / modeled / investigating / adjudicating / closed / rejected`
- 风险等级：`low / medium / high`
- 调查任务状态：`queued / assigned / in_progress / completed / cancelled`

案件、风险与调查任务枚举在 `backend/src/constants/enums.py` 和 `frontend/src/utils/constants.js`。线索状态、凭证来源和复核状态用于 `backend/migrations/001_schema.sql`、`backend/migrations/002_clue_reviews.sql`、`backend/src/schemas/clue_reviews.py` 和 `frontend/src/utils/constants.js`。

补件渠道 `phone / sms / email` 见 `backend/migrations/003_document_followups.sql`、`backend/src/schemas/claims.py` 与 `frontend/src/pages/documentTriage.js`。队列状态由 `backend/src/services/document_triage_service.py` 计算，前端负责展示与筛选。

付款单状态 `reserved / paid / rejected / suspended`、回执结果 `confirmed / rejected / mismatch` 见 `backend/migrations/004_payments.sql`、`backend/src/constants/enums.py`、`backend/src/schemas/payments.py` 与 `frontend/src/utils/constants.js`。额度占用与状态机逻辑集中在 `backend/src/services/payment_service.py`。
