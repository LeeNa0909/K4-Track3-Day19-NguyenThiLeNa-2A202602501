# Báo cáo Day 19 — Flat RAG vs GraphRAG

**Họ tên:** Nguyễn Thị Lê Na  **MSSV:** 2A202602501  **Ngày:** 2026-10-05

## 1. Chi phí (10 điểm)

```text
Chat model: openrouter:openai/gpt-4o-mini | Embedding: openrouter:openai/text-embedding-3-small | top_k=3 | chunk_size=800 | chunks=176 | KG: 205 nodes / 379 rels

== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176     56072        0   0.00112     84.8
graph       196     91958     4573   0.00925    144.9

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.43   1.00      694       47   0.00013     2.37
graph       0.69   1.33     3233       78   0.00052     2.81
```

| Chỉ số | Flat | Graph | Graph / Flat |
| --- | ---: | ---: | ---: |
| Indexing USD | 0.00112 | 0.00925 | 8.26× |
| Indexing giây | 84.8 | 144.9 | 1.71× |
| Mỗi câu: USD | 0.00013 | 0.00052 | 4.00× |
| Mỗi câu: giây | 2.37 | 2.81 | 1.19× |
| Mỗi câu: `in_tok` | 694 | 3233 | 4.66× |

Phần indexing của GraphRAG có thêm 20 lần gọi pipeline so với Flat, dùng thêm 35,886 input tokens và 4,573 output tokens để trích xuất graph. Khi hỏi đáp, context graph dài hơn: trung bình 4.66 lần input tokens và 4 lần chi phí mỗi câu. Đổi lại, recall trung bình tăng từ 0.43 lên 0.69 và judge trung bình từ 1.00 lên 1.33; mức tăng không đồng đều ở từng câu.

Về chi phí thuần, GraphRAG không hòa vốn với Flat trong benchmark này: phần tăng thêm xấp xỉ `$0.00813 + $0.00039 × số câu hỏi`, vì cả indexing lẫn mỗi truy vấn đều đắt hơn. Với 20 câu hỏi sau khi dựng index, phần tăng thêm khoảng `$0.01593`; nên chọn GraphRAG khi cần truy vấn nối hai KB, không phải để giảm chi phí.

## 2. Từng câu hỏi (10 điểm)

| Câu | Loại | Flat recall / judge | Graph recall / judge | Thắng | Vì sao |
| --- | --- | ---: | ---: | --- | --- |
| Q1 | single-hop-law | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai tìm đúng định nghĩa tiền chất ở Điều 2 Luật PCMT. |
| Q2 | single-hop-news | 1.00 / 2 | 1.00 / 2 | Hòa | Cả hai nêu đúng Trần Thanh Tuấn và Trần Minh Tâm lãnh án tử hình. |
| Q3 | cross-kb | 0.00 / 0 | 1.00 / 2 | Graph | Graph nối vụ Lê Minh Thành qua tội danh đến Điều 251, khoản 1 và khung 2–7 năm; Flat không trả lời được. |
| Q4 | cross-kb | 0.00 / 0 | 0.00 / 0 | Hòa | Cả hai không trả lời được mức tối đa; context graph chỉ lấy khoản 1 dù graph có khoản 4 Điều 255. |
| Q5 | cross-kb-multi-hop | 0.60 / 1 | 0.80 / 1 | Hòa theo judge; Graph recall cao hơn | Graph lấy đúng tội vận chuyển và lượng MDMA nhưng câu trả lời ghi nhầm Điều 251; graph liên kết vụ này với Điều 250. |
| Q6 | aggregation | 0.00 / 1 | 0.33 / 1 | Hòa theo judge; Graph recall cao hơn | Graph liệt kê các vụ mục tiêu theo tên vụ nhưng gán nhầm lượng 0,686g cho vụ Viện Pháp y và thêm vụ TP.HCM 36kg không có cạnh MDMA. |

## 3. Phân tích lỗi (20 điểm)

### Lỗi E2: Thiếu ngữ cảnh luật

- **Hiện tượng:** Q4 hỏi hành vi của Hoàng Nato và mức phạt tù tối đa. Câu trả lời GraphRAG là `Không đủ thông tin.` dù graph có Điều 255 và khoản 4 với mức phạt tối đa.
- **Bằng chứng:** Truy vấn graph xác nhận hai khoản của Điều 255; lần gọi `context()` với tài liệu Hoàng Nato chỉ đưa khoản 1 vào context, không đưa khoản 4:

```cypher
MATCH (k:Case {doc_id:'news-100260925144412498'})-[:CHARGED_WITH]->(c:Crime)<-[:DEFINES]-(a:Article)
WHERE a.id CONTAINS '255'
MATCH (a)-[:HAS_CLAUSE]->(cl:Clause)
WHERE cl.number IN [1,4]
RETURN k.name, c.name, a.id, cl.number, cl.penalty
```

```text
Vụ triệt phá 8 đường dây ma túy tại TP.HCM | tổ chức sử dụng trái phép chất ma túy | Điều 255 BLHS | khoản 1 | phạt tù từ 02 năm đến 07 năm
Vụ triệt phá 8 đường dây ma túy tại TP.HCM | tổ chức sử dụng trái phép chất ma túy | Điều 255 BLHS | khoản 4 | phạt tù 20 năm hoặc tù chung thân
```

Trong kết quả `context()`, fact luật cho Điều 255 chỉ là khoản 1. Cùng vụ có cạnh `INVOLVES` tới `etomidate`, còn khoản 4 Điều 255 không có cạnh `MENTIONS` chất này; bộ lọc của KG-3 vì thế không chọn khoản 4.
- **Nguyên nhân:** Lỗi ở truy xuất KG-3: luôn lấy khoản 1 và chỉ lấy khoản khác nếu có chất chung giữa vụ với `MENTIONS` của khoản. Điều kiện “phạt tù tối đa” trong câu hỏi không được dùng để chọn khoản.
- **Đề xuất sửa:** Với câu hỏi có “tối đa”, “cao nhất” hoặc “mức phạt”, lấy khoản có khung cao nhất của Điều vừa tìm được (hoặc tất cả khoản của Điều đó). Cách này tăng độ dài context và token nhưng tránh bỏ sót khung phạt.

### Lỗi E5: Câu trả lời LLM lệch với graph trong câu tổng hợp

- **Hiện tượng:** Q6 hỏi các vụ có liên quan MDMA. Câu trả lời GraphRAG nói vụ Viện Pháp y có 0,686g MDMA và thêm vụ TP.HCM hơn 36kg ma túy là có MDMA. Trong graph, lượng 0,686g gắn với vụ Sầm Sơn; vụ TP.HCM chỉ có cạnh với chất chung `ma túy`, không có cạnh MDMA.
- **Bằng chứng:** GraphRAG trả lời:

```text
3. Vụ án tại Viện Pháp y tâm thần Trung ương: Có thu giữ 0,686g ma túy MDMA.
4. Vụ mua bán hơn 36kg ma túy tại TP.HCM: ... trong đó có MDMA.
```

Truy vấn các vụ có cạnh MDMA cho kết quả:

```cypher
MATCH (k:Case)-[r:INVOLVES]->(s:Substance)
WHERE toLower(s.name) CONTAINS 'mdma'
RETURN DISTINCT k.name, k.doc_id, s.name, r.amount
ORDER BY k.doc_id
```

```text
Vụ vận chuyển ma túy từ Đức về Việt Nam | news-100260917203001265 | MDMA | 9.6kg
Vụ góp tiền mua ma túy tại Hà Nội | news-100260918080821054 | MDMA | 5 viên
Vụ án tại Viện Pháp y tâm thần Trung ương | news-100260924105118645 | MDMA | (rỗng)
Vụ tổ chức sử dụng ma túy tại Sầm Sơn | news-100260930085028036 | MDMA | 0,686g
```

Kiểm tra riêng vụ TP.HCM cho thấy graph chỉ ghi `ma túy | 36kg`, không phải MDMA:

```cypher
MATCH (k:Case {doc_id:'news-100260928173914514'})-[r:INVOLVES]->(s:Substance)
RETURN k.name, s.name, r.amount
```

```text
Vụ mua bán hơn 36kg ma túy tại TP.HCM | ma túy | 36kg
```

Câu trả lời còn bỏ vụ Sầm Sơn dù đây là vụ có cạnh MDMA và lượng 0,686g.
- **Nguyên nhân:** Lỗi ở bước tổng hợp/câu trả lời KG-4: LLM trộn lượng chất giữa các vụ và suy diễn từ “ma túy” chung sang MDMA, thay vì chỉ dùng các cạnh MDMA được truy xuất.
- **Đề xuất sửa:** Với aggregation, tạo danh sách đóng từ truy vấn `Case-[:INVOLVES]->Substance {name: 'MDMA'}`; chỉ cho LLM trình bày các hàng đó và lượng nằm trên đúng cạnh. Tốt hơn nữa, để code dựng câu trả lời danh sách trực tiếp, dùng LLM chỉ để diễn đạt.

## 4. Kết luận (5 điểm)

Flat RAG đủ cho truy vấn một nguồn như Q1–Q2: hai bên đều đạt recall 1.00 và judge 2, còn indexing Flat rẻ hơn 8.26 lần. GraphRAG có lợi rõ ở Q3 khi phải nối tin với luật (judge 2 so với 0); ở Q5–Q6 recall cao hơn Flat nhưng judge vẫn bằng nhau vì câu trả lời còn sai hoặc thiếu chi tiết. Q4 cho thấy quan hệ cầu chưa đủ nếu KG-3 bỏ khoản luật phù hợp. Do đó nên dùng Flat cho câu hỏi đơn nguồn và ưu tiên GraphRAG khi cần nối hai KB, sau khi sửa chọn khoản và ràng buộc phép tổng hợp vào kết quả Cypher.

## 5. Tự kiểm (5 điểm)

### Tests

```text
$ .\.venv\Scripts\python.exe -m pytest tests/ -q
52 passed, 2 subtests passed in 0.16s
```

### Benchmark đầy đủ đối chiếu với kết quả ở mục 1–4

Các số liệu dưới đây được chép từ `ket_qua_benchmark_kg.txt`:

```text
Chat model: openrouter:openai/gpt-4o-mini | Embedding: openrouter:openai/text-embedding-3-small | top_k=3 | chunk_size=800 | chunks=176 | KG: 205 nodes / 379 rels

== Indexing (one-off)
pipeline  calls    in_tok  out_tok       USD  seconds
flat        176     56072        0   0.00112     84.8
graph       196     91958     4573   0.00925    144.9

== Querying (mean per question)
pipeline  recall  judge   in_tok  out_tok       USD  seconds
flat        0.43   1.00      694       47   0.00013     2.37
graph       0.69   1.33     3233       78   0.00052     2.81
```

### Kiểm tra hợp đồng bằng `--check`

Log `--check` mới nhất do người dùng cung cấp:

```text
$ .\.venv\Scripts\python.exe .\bench_kg.py --check
[OK] Dữ liệu: 18 điều luật, 20 bài báo
[OK] KG-1 link_entity
[OK] Neo4j kết nối được
[provider] chat = openrouter:openai/gpt-4o-mini | embedding = openrouter:openai/text-embedding-3-small
[OK] KG-2 build_graph: 205 node / 379 cạnh, đường xuyên 2 KB dài 2 cạnh
[OK] KG-3 context: 13 dữ kiện, có Điều 251
[OK] KG-4 GraphRAGAgent.answer
[OK] Chi phí check: 1 lần gọi LLM, $0.00065.
```

Số node/cạnh trong log này trùng với benchmark đầy đủ: **205 nodes / 379 relationships**. Tuy nhiên, `ket_qua_benchmark_kg.txt` mới là nguồn cho chi phí và chất lượng trả lời Flat-vs-Graph ở mục 1–4; $0.00065 là chi phí riêng của lần `--check`. Trong bản `bench_kg.py` hiện có ở workspace, `--check` chỉ truyền một bài báo vào `build_graph`; vì vậy cần xác nhận lệnh được chạy từ đúng bản code trước khi kết luận graph đầy đủ đã được nạp. Trong lần dựng graph đầy đủ đã đối chiếu, bảy label `Article`, `Case`, `Clause`, `Crime`, `Location`, `Person`, `Substance` và bảy loại quan hệ `CHARGED_WITH`, `DEFINES`, `HAS_CLAUSE`, `INVOLVED_IN`, `INVOLVES`, `LOCATED_IN`, `MENTIONS` khớp ontology đã nộp.


## Vấn đề gặp phải (không tính điểm)
