"""Sub-paket optimasi CV berbasis LLM (M8 Wave 5).

- `prompts`: perakit pesan system/user + aturan grounding BEKU + skema JSON.
- `llm_client`: adapter Groq (retry + fallback model, tanpa jaringan di test).
- `grounding_validator`: validator grounding R1-R4 (pertahanan kedua server).
- `pdf_renderer`: perender PDF CV hasil optimasi (ReportLab, tanpa gambar).
"""
