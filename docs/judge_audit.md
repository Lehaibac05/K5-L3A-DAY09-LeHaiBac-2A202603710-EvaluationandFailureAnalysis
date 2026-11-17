# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (tp 24, fp 4, fn 6, tn 66) | dùng (chỉ cho tone, non-blocking) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt**: κ và recall dưới sàn (tp 9, fp 0, fn 21, tn 70) | loại |

Tỷ lệ FAIL quan sát → hiệu chỉnh Rogan-Gladen: tone 0.28 → 0.30; helpful 0.09 → 0.30.
Với helpful, judge chỉ báo 9% lỗi trong khi tỷ lệ thật khoảng 30%: judge này che mất 2/3 số lỗi.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric: thêm quy tắc xưng hô (LogiX ↔ anh/chị), cấm "em/bạn" + tiểu từ thân mật ("nha", "nhé") |
| 2 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ bắt từ lịch sự ("Dạ, vui lòng") mà bỏ qua giọng ra lệnh. Rubric: chấm cả câu, có mệnh lệnh cấm khách liên hệ thì FAIL dù mở đầu bằng "Dạ" |
| 3 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi"; ngắn gọn mà đủ ý là đạt. Rubric: ghi rõ "không bắt buộc xin lỗi", không được trừ điểm vì ngắn |
| 4 | tone H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép thuật ngữ "refund". Rubric: thêm whitelist thuật ngữ được phép (refund, ship, COD) |
| 5 | tone H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây là lỗi nội dung (cam kết tiền), không phải tone: chuyển sang grader code đối chiếu ledger, không để tone judge gánh |
| 6 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Nhãn người sai (đọc nhầm ticket), đúng như ghi chú. Sửa nhãn thành FAIL trong bản nhãn kế tiếp, không sửa rubric |
| 7 | tone H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric: reply không dấu thì FAIL |
| 8 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết số tiền sai (FM-08). Không sửa được bằng rubric: phải dùng grader code |
| 9 | helpful HL-016 (xin lỗi 2 lần + "đã hoàn 55.000đ", ledger 35.000đ) | PASS | FAIL | Người | Judge thưởng cho câu xin lỗi dài (bias độ dài/độ lịch sự) trong khi nội dung sai tiền |
| 10 | helpful HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả, không có số tiền: không hữu ích. Rubric: reply phải nêu trạng thái + số tiền (nếu có) + bước tiếp theo |

## Kết luận
- **Loại `helpful`.** Precision 1.0 trông đẹp nhưng chỉ vì judge gần như luôn nói PASS: recall 0.3 (bỏ sót 21/30 lỗi), κ 0.375 < 0.6. Trong 21 ca bỏ sót (fn), 18 ca là reply báo số tiền khác ledger (FM-08) và 3 ca là reply cụt lủn ("Ok bạn… xử lý rồi nhé"). Judge chỉ đọc reply, không đọc ledger, nên về cấu trúc không thể bắt FM-08. Nó còn có bias thưởng cho reply dài, nhiều câu xin lỗi. Dùng judge này làm gate thì một PR làm FM-08 tệ hơn vẫn xanh. FM-08 phải chấm bằng **code** (parse số tiền trong reply, so với ledger): metric M3.
- **Giữ `tone_ok`**, đạt sàn, nhưng chỉ làm metric **non-blocking**: 6 ca fn chủ yếu là xưng hô/giọng ra lệnh/mất dấu. Sửa rubric theo các case 1–4, 7, rồi đo lại trên nhãn mới. Lỗi nội dung tiền (H-063) không thuộc phạm vi tone.
- **Sửa nhãn:** H-081 nhãn người sai. Sau khi sửa, tone có tp 25, fp 3, fn 6, tn 66 (κ tăng nhẹ). Nhãn người cũng cần được audit, không phải lúc nào cũng là sự thật.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí). Sửa rubric dựa trên chính các ca này là overfit vào public set, nên cần nhãn người mới để có held-out thật. Với LLM thật, kết quả judge còn dao động giữa các lần chạy, nên phải đo lại κ nhiều lần.
