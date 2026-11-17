# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / eval set SHA:**
- **Phiên bản:** code (commit) … · eval set v1 (sha …) · metric_spec … · grader (commit) … · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed, nguồn lab8_public; nhãn: labels_v1.json
- **Metric & ngưỡng:** (trích metric_spec.yaml)
- **Kết quả baseline vs PR:** bảng + paired CI
- **Judge:** tone_ok κ=0.757, P=0.857, R=0.800 (đạt sàn, dùng non-blocking); helpful bị loại vì κ=0.375, R=0.300: bỏ sót 21/30 lỗi, 18 trong đó là reply nói số tiền khác ledger (FM-08) mà judge không thể thấy. Chi tiết: `docs/judge_audit.md`.
- **Trace case:** link `docs/trace_case.md`, bước sai đầu tiên, regression test
- **Gate owner:** ai xử lý khi gate exit 1
- **Phạm vi pilot:** …
- **Giới hạn / bằng chứng còn thiếu:** MockLLM, 14 item, judge replay; không đo trên người dùng thật
- **Khi nào tăng eval-set version:** …

## v2 (M5–M7)

- **Eval set v2:** 28 item = 14 item v1 + 14 claim adversarial (`data/eval/adversarial_v2.json`), sha `55fad3c85cdf`. Cơ chế tấn công → FM qua `config/fm_map.yaml`; mỗi FM bị tấn công có ≥3 item (FM-02 4, FM-03 4, FM-04 5, FM-05 5, FM-06 3, FM-07 5, FM-08 4, FM-09 4).
- **Slice gate** (`config/metric_spec_v2.yaml`, metric `pass_rate`, đều blocking + `no_significant_drop`):

| Slice | n item | Sàn | swarm (baseline) | Bắt lỗi nào |
|---|---|---|---|---|
| money_movement | 12 | 0.95 | 1.000 | `slice_regression` (cộng clause ở seed lẻ): trung bình chung 0.936 vẫn trên sàn 0.85, CI [−0.121, +0.029] chạm 0, nhưng slice này 0.850 → BLOCK |
| adversarial | 14 | 0.95 | 0.971 | Tấn công v1 chưa có (FM-03/06 injection, clause cũ/tương lai); `slice_regression` 0.914 |
| denial | 11 | 0.90 | 0.945 | FM-02 ignore_denied (`seeded_regression` 0.364) |
| escalation | 4 | 0.95 | 1.000 | FM-09 cross_principal: không có "trung bình" cho việc lộ đơn của người khác |

  Sàn đặt dưới baseline swarm của từng slice và trên mức mà một regression chỉ ở 1 slice để lại. `fixed` và `honest_refactor` đạt 1.000 ở mọi slice (0 báo nhầm).
- **Scorecard** `lab9.mutation`: 3/3 regression bị chặn, 0 báo nhầm.
- **Giới hạn cỡ mẫu:** slice nhỏ (escalation 4 item, FM-06 chỉ 3 item) nên CI rất rộng; slice gate ở đây dựa vào sàn tuyệt đối nhiều hơn là CI. Bug chỉ xuất hiện ở 1/3 seed không được phát hiện ổn định với 5 seed.
