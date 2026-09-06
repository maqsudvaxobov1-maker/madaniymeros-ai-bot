Madaniy Meros AI — V14 STRICT LEGAL 846

Render:
Build Command: python -m py_compile app.py
Start Command: python app.py

Files:
app.py
knowledge_base_full_4.json
requirements.txt
render.yaml

V14 changes:
- 846 exact-object claims are blocked unless full list source is present.
- Generic 846 answers explicitly disclose when full list is not connected.
- Internal “Manba 1/2/3” labels are removed from strict context.
- Legal document types and authorities are kept separate.
- No unsupported legal authority/rule inference.
- CCTV is not automatically classified as construction without source support.
- Archaeology permit/open-sheet/council concepts are separated.
