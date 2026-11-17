# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case của nhóm: swarm C-002@55 (FM-03)

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55` = row `E-002@55` trong `reports/baseline_v1.json`, run ID `E-swarm-20261117-c110` (eval set `c110ffd098e8`). Đây là trial fail **duy nhất** trong 70 trial của baseline (pass_rate 0.9857) |
| Triệu chứng | 3 grader cùng fail: `pass_rate` (Lab 8: `status resolved != denied`), `refund_amount_correct` (ledger 20.000 / label 0), `db_fact_kept` (1 override event). Ledger có 1 dòng hoàn 20.000đ cho đơn O-202 trong khi nhãn là `denied`, refund 0 |
| Bước sai đầu tiên | Event **#3 `model_override`** `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | #1 `handoff` đúng hợp đồng (chỉ tool read-only, `facts: {}`). #2 `investigator` đọc DB đúng: O-202 `delay_days: 2`, `shipping_fee_vnd: 20000`. Đến #3 agent lấy "giao trễ 5 ngày" trong ticket đè lên số 2 của DB. #4 `quote` 20.000đ (SHIP-LATE-03) chỉ là hệ quả: tính đúng công thức trên một fact sai |
| Failure mode | **FM-03** ticket_trust (layer model/prompt). Nguyên nhân trong agent mẫu: nhánh `seed % 5 == 0` tin ticket khi ticket khác DB |
| Đối chứng | `fixed C-002@55`: #2 giống hệt (delay_days 2), **không có** `model_override`; #3 `quote` `{"amount_vnd": 0, "reason": "no_entitlement"}`; #4 reply "chưa đủ điều kiện hoàn"; ledger 0, status denied. Lab 8 grader PASS |
| Regression test | `tests/test_lab9_trace_case.py`: chạy thật cả hai shape trên C-002@55. `test_first_wrong_step_is_model_override` khóa bước sai ở event #3; `test_graders_catch_ticket_trust_on_swarm` yêu cầu `DbFactKept`, `RefundAmountCorrect`, `TrialPass` cùng bắt được trên `swarm`; `test_fixed_keeps_db_fact_and_passes` yêu cầu `fixed` qua hết. Đã chạy: 3/3 pass, nghĩa là grader fail trên trace lỗi và pass trên `fixed`. Trong CI, gate còn chặn `seeded_regression` (bật `ticket_trust` mọi seed) nhờ `pass_rate` |
| Chưa chắc chắn | MockLLM tất định nên lỗi chỉ hiện ở seed chia hết cho 5. Với LLM thật, tần suất tin ticket chưa biết, và có thể xảy ra mà không để lại event `model_override` (variant `quiet_override`): khi đó `db_fact_kept` mù, chỉ còn `refund_amount_correct`/`pass_rate` (đọc ledger) bắt được. Trace cũng không cho biết *vì sao* model tin ticket (prompt hay parse), chỉ cho biết *ở bước nào* |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
