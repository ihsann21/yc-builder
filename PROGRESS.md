# PROGRESS — Build the Builder

Çalışma günlüğü. En yeni giriş en altta. Her kayda değer adımdan sonra güncellenir (kural: `CLAUDE.md`). Ayrıntılı tasarım `build_the_builder_final_plan.md`'de; burası "ne yaptık, ne öğrendik, sırada ne var".

## 10 Ekim, sabah: plan ve kaynaklar

Hackathonun görevi: bir bankanın brief'ini (tahsilat araması kuralları) okuyup Freya'da telefon ajanını (workflow) kendi başına kuran bir builder yazmak. Puanı yalnızca o ajanın gizli müşterilerdeki başarısı belirliyor: 2 gizli brief × 30 müşteri = 60 vaka; bir müşteri ancak 3 koşunun üçünde de geçerse sayılıyor; kontrol = bankanın kayıtları (ledger) + brief'e uyum + dürüstlük. Gizli brief'ler Pazar 20:00'de (İstanbul) geliyor, teslim 23:00; builder brief başına en çok 30 dakika çalışabilir; ilk 10 takımın builder'ını organizatör yeniden çalıştırıyor.

Plan önce kickoff toplantısı ve challenge sayfasıyla (v1.4, Bölüm 2.7), sonra kit'in 16 dosyasıyla (v1.5, Bölüm 2.8) güncellendi. Öğrenilen en önemli olgular: ajan Freya'da bir workflow (adımlar, koşullu rotalar, kod düğümleri); her turda üç ayrı model çağrısı var ve rota seçen model prompt'u görmüyor; banka brief'i zorlamıyor, kuralları yalnız ajan koruyor; tarih hesabı `now` değişkeninden kodla yapılmalı; ajan modeli herkes için aynı (`experimental-5`); workspace'te aynı anda tek simülasyon koşuyor.

## 10 Ekim, 15:15: kurulum

Kit `build-the-builder-v3/build-the-builder/` altında (sürüm 3). `env.sh` hazır ve `.gitignore`'da (Freya anahtarı, takım anahtarı). Python 3.11. `claude-agent-sdk` kuruldu; API anahtarı olmadan, VS Code eklentisinin Claude girişiyle çalışıyor (test: "OK", $0,36; şişkin maliyet kullanıcının genel Claude ayarları yüklendiği için, builder'da `setting_sources=["project"]` ile olmaz). Repo kökünde `scripts/new_session.py`: bir pratik vaka için banka oturumu açar, çağrı değişkenlerini ve güvenlik cevaplarını basar (dashboard ya da sohbet testi için).

## 10 Ekim, 15:25–16:03: taban ölçümler (B0)

Kit'in örnek ajanı (`examples/base-agent.json`, 2 adım, 4 tool) Brief A'da **0/10**. Nedenler: tatil ve son tarih bilinmiyor (PUB-04, 07), zorunlu cümleler eksik (SMS cümlesi PUB-01, "kalan gecikmede kalır" PUB-06, "1 iş günü" PUB-08), sonuç ve neden çağrı sonrası tahminle yanlış (PUB-03, 05, 08), eksik tool'lar (geri arama PUB-02, devir PUB-09), tool hatasında tekrar yok (PUB-10). PUB-01'in kaydı doğruydu, tek bir cümle yüzünden kaldı: brief'in "çoğu hata atlanmış tek bir kuraldan" uyarısı birebir doğru.

Kit'in örnek builder'ı (`examples/agent_builder.py`, Claude Agent SDK, model `claude-opus-5-5`) iki kez çalıştırıldı. Workflow'u elle değil, bir Python üretici betikle (`out/gen_brief_*.py`) kurdu: kodla tarih ve ürün hesabı, aşama başına bir adım (setup, greet, identity, load_account, account_facts, negotiate), çağrı sonunda otomatik `close_call`.

| Koşu | Süre | Maliyet | Kendi testi (tek koşu) | 3 tekrarlı ölçüm |
| --- | --- | --- | --- | --- |
| A+B girdisi → `brief-b` ajanı | 10 dk 51 sn | $2,11 | B: 2/3 → 2/3 → 3/3 | **B: 2/3** (PUB-13 bir koşuda geri okumada düştü) |
| A girdisi → `brief-a` ajanı | 10 dk 16 sn | $1,81 | A: 5/10 → 9/10 → 10/10 | **A: 10/10** |

**B0 = 12/13 (3 tekrarla).** Pratik vakalarda çıta neredeyse tavanda. Ama bu skor gizli brief'i abartıyor: builder `public-test-set.json`'u (beklenen sonuçlar ve hakemin kontrolleri) okuyup ona göre ayarladı; gizli brief'te bu dosya ve büyük olasılıkla test edilecek vaka yok.

## 10 Ekim, 16:05–16:19: dersler

1. Uzun tek prompt'taki kurallar 3/3'te sallanıyor (PUB-13 geri okuma, PUB-12 teklif sırası). Kural ne kadar koda ve rotaya geçerse o kadar tutarlı.
2. Hakem kelimeye hassas: açılıştaki "This call is recorded" sözü, söz kaydedilmeden "recorded" demek sayıldı.
3. Builder kendi kodunda tool sonucunu yanlış değişken adından okudu (5/10'un nedeni). Değişken adları ve `data.` yolları kitaplıkta sabitlenmeli.
4. Dashboard testinde `customer_id` yoktu; banka `404 unknown customer_id` döndü, ajan bunu "doğum tarihi yanlış" diye müşteriye söyledi. Tool hatası ile yanlış cevap ayrılmalı (kancada `ok:false/error` ≠ `verified:false`).
5. Kit builder'ı `cat env.sh` çalıştırdı; Freya ve takım anahtarı trace'e (`traces/20261010-152917.jsonl`) girdi. Bizim builder `env.sh` okumayacak, trace'te anahtar olmayacak, commit öncesi `fak_` taraması yapılacak.

## 10 Ekim, 16:25: oturum devri

`PROGRESS.md` ve repo kökünde `CLAUDE.md` açıldı. `CLAUDE.md` yeni oturumun okuma sırasını (önce bu dosya, sonra planın ilgili bölümleri, sonra kit) ve sert kuralları içeriyor. Yan etki: kit builder'ı kit klasöründe çalışırken üst klasördeki `CLAUDE.md`'yi de yükleyebilir; bizim `build.py` ayar kaynaklarını boş vererek bundan yalıtılacak.

## 10 Ekim, 16:30–17:40: ortak çekirdek (`builder/lib/`)

İki üretici betik yan yana okundu, mekanizmalar brief değerlerinden ayrılıp `builder/lib/` altına yazıldı. İki katman var. **Runtime** (`runtime/`: `common`, `dates`, `products`, `hooks`, `closing`) Freya'nın kod düğümlerinde ve kancalarında koşan kod; normal Python modülü olarak test ediliyor, kaynağı olduğu gibi snippet'e gömülüyor (yalnız giriş fonksiyonunun eriştiği tanımlar, docstring ve yorum satırları boşaltılmış, satır numaraları korunuyor); config parantezsiz bir literal olarak ekleniyor (`{` → `\x7b`), yani config metni hiçbir yoldan `{{` üretemiyor. Kurallar testle bağlı: yalnız json/re/datetime, izinli builtin listesi (kit A snippet'lerinin kullandıkları), `_` ile başlayan ad yok, f-string yok, giriş fonksiyonu asla hata fırlatmaz. **Builder tarafı:** `embed` (snippet kurma, statik kontrol, kısıtlı yerel koşucu), `calc` (tarih ve ürün kod düğümleri), `hooks` (pre: normalizasyon, ürün kimliği onarımı, tarihi sınıra ve iş gününe çekme; post: header silme, yazma sayacı, tekrar/vazgeç, kurallı `what_to_do_next`), `closing` (`close_call` sonucu için sıralı kural dili), `tools` (OpenAPI okuma, `api_call`/`end_call` tool'u) ve `workflow` (düğüm/koşul yardımcıları, platformun sessiz silmelerini yakalayan statik `check`). Son ikisini paralel bir ajan yazdı (171 test, 3.10 ve 3.11; `api_tool` kit'in 9 tool'unu, düğüm yardımcıları A workflow'unu birebir yeniden kuruyor). Kancalar ile kapanış `bb_` önekli durum değişkenleriyle konuşuyor (`bb_count__<tool>`, `bb_last__<tool>__<alan>`, `bb_log__…`, `bb_identity`, `bb_products`, `bb_deadline__<id>`).

Ölçüm (yerel, ağsız): **410 test yeşil, kapsama %95** (pytest-cov). Kit'in elle yazdığı snippet'lerle fark testleri: tarih kodu 181 gün × 3 saatte birebir (son tarihler, ilk teklif günü, this/next ve takvim satırları); `account_facts` metni A ve B'de 4 tarih × 160 rastgele ürün setinde birebir; VERIFY/PROMISE/CALLBACK kancaları aynı; kapanış kancası A ve B ızgarasında 1000'den çok durumda aynı sonuç. `dev/practice_a.py` kitaplıkla pratik Brief A workflow'unu kuruyor (prompt'lar kit JSON'undan aynen, tesisat bizim): `check()` boş; çevrimdışı uçtan uca 6 senaryo (söz, iki kez hata, sözden sonra devir, kimlik başarısız, geri arama, modelin seçimi) doğru sonucu yazıyor. `tests/test_no_brief_values.py` brief'lerden ve OpenAPI'den belirteçleri otomatik çıkarıp `builder/`'ı tarıyor: temiz. **Ölçülmedi:** platformda hiçbir şey koşulmadı (dry run, chat, simülasyon yok).

Bulgular: (1) Kit'in B kapanış kancası `all()` kullanıyor; not tabanlı kapanış yolu pratikte hiç sınanmamış (13 vakada B'lerin hepsi `promise`). Freya sandbox'ında `all` yoksa bu yol sessizce bozuk; bizim runtime onu kullanmıyor. (2) Kit'in `strftime('%B')`'si içeride `time` modülünü içe aktarıyor; bizim tarih kodu ay adlarını tablodan alıyor. (3) Boyut: bizim A workflow'u 191 KB (kit'inki 37 KB). Genel kod kanca başına 9–15 KB. Platformun gövde sınırı belgelenmemiş; dry run ile bakılmalı. (4) `scripts/new_session.py` kullanıcı tarafından silindi (gereksizdi).

## 10 Ekim, 18:05–18:35: inceleme düzeltmeleri, `build.py` + skill, ilk koşu

Bağımsız inceleme (python-reviewer): kritik yok; 1 yüksek (telefon hanesi normalizasyonu "4821 ... 2019" girdisinden "2019" çıkarıp tahmin ediyordu) ve 6 orta bulgu (tutar/tarih/saat tahmini, pre-kancanın tek alanda çökmesi, kapanışta devrin kaybolması, bant dışı günde boş son tarih, virgüllü not, biçim değişikliğinde boş not). Hepsi düzeltildi, testleri eklendi: 429 test yeşil. Yeni: `builder/build.py` (Agent SDK, skill sistem prompt'una ekli, 25 dk sınırı, anahtarlar maskeli trace, `env.sh`/anahtar/`dev`/`tests`/kit `out` erişimini reddeden PreToolUse kancası, export), `builder/save.py` (check → dry run → kaydet/yayınla → geri okuma), `builder/skill/SKILL.md` (brief'ten bağımsız kurallar, kitaplığın tek sayfalık API'si, `gen.py` şablonu).

İlk koşu (pratik Brief A, `--cases A`, kullanıcı başlattı 18:20): ajan 3. dakikada workflow'u kaydetti (199 KB; dry run ve kayıt geçti, boyut sorunu yok), sonra `run_cases` sırasında **benim trace'im** Windows konsolunda `→` karakterinde `UnicodeEncodeError` verip ajanı öldürdü (build 255 sn, export çalıştı). Düzeltildi: stdout UTF-8, tracer asla hata fırlatmaz; ayrıca göreli yollar repo köküne göre de çözülüyor, test çıktıları trace'e giriyor. Öksüz kalan simülasyon Freya'da tamamlanmıştı; ledger ile yeniden puanlandı (salt okuma): **8/10, tek tekrar** (kit builder'ının ilk koşusu 5/10'du). Kalanlar: PUB-07 (tatil günü istenince bir sonraki iş günü yerine son tarih önerildi; builder'ın prompt'u), PUB-05 (zor durumda neden `refused` yazıldı, beklenen `hardship`; karar modelin doldurduğu nedende, kitaplık hatası değil). Teşhis için kapanış kancası artık modelin seçimini `bb_close_model`'e yazıyor. Ajanın düzeltme turları koşmadı; yeniden koşu gerekiyor.

## Kararlar

- **Yol B (karma):** kit'in ajan tabanlı builder'ı temel; üstüne bizim skill'lerimiz ve test edilmiş yardımcı kod parçalarımız (tarih ve iş günü, ürün başına son tarih ve geri okuma, deneme sayaçları, deterministik `close_call` sonucu, "sırada ne var" kancaları). Planın ağır kısımları (AgentSpec, iki sağlayıcı, τ vekil benchmark) kullanılmıyor; plan akşam sadeleştirilecek.
- **Düzeltme kuralı:** düzeltme brief'e değil mekanizmaya yapılır; brief değeri (tatil, tutar, sonuç adı) koda yazılmaz.
- **Genelleme testi, sınırlı:** 1 biçim mutasyonu (Brief A ham malzeme biçiminde: e-posta, politika alıntısı, memo, kod listesi; beklenen sonuçlar aynı) + 2–3 kural mutasyonu (aynı 13 müşteri, farklı kurallar, beklenen sonuçlar elle). Müşteri verisi bankada sabit; kimlik soruları ve görüşme tarihi değiştirilemez.
- **Tesisat kitaplıktan gelir:** builder (ajan) Freya içinde koşan kodu kendisi yazmaz; `builder/lib/` fonksiyonlarına brief'ten okuduğu config'i verir. Normalizasyon asla tahmin etmez: emin olunamayan değer olduğu gibi gider (yanlış güvenlik cevabı müşterinin aleyhine sayılır, okunamayan sayılmaz). Pratik brief değerleri yalnız `dev/` ve `tests/` altında (`dev/practice.py`).

## Açık sorular (destek kanalı)

19: ilk 10'un yeniden koşusunda builder'ın Claude anahtarını kim veriyor? · 23: gizli brief'lerin tool API'si pratik bankayla uyumlu mu, build sırasında test oturumu açılabiliyor mu? · 24: workflow sınırı 10 mu (site), 200 mü (kit README)?

## Kayıtlar

- Freya workflow'ları: `base` 0a1a92e1…, `brief-b` e6772bee… (agent 28027619…), `brief-a` 270d0e30… (agent 68a8b1f8…). Yerel eşleme: kit'te `.freya-agents.json`.
- Sonuçlar: kit'te `results/` (`base-A.json`, `b0-B-reps3.json`, `b0-A-reps3.json`, `b0-builder*.log`, `log.jsonl`). Trace'ler: `traces/` (anahtar içeriyor, paylaşılmaz).
- Commit edilmemiş: `builder/`, `tests/`, `dev/`, `pytest.ini`, `.gitignore` eki (`__pycache__/`, `.coverage`, `.pytest_cache/`, `dev/out/`). Testler: kökte `python -m pytest -q` (ağsız, ~6 sn).

## Sıradaki

1. **Kitaplığı platformda doğrulamak (onay gerekiyor).** `python -m dev.practice_a` çıktısını `freya.validate_workflow` (dry run) ile doğrula: 191 KB kabul ediliyor mu, alan silinmesi var mı. Sonra `lib-a` yuvasına kaydet, bir chat turu, ardından `run_cases.py --brief A --reps 3` ile kit ajanına (B0 A: 10/10) karşı ölç. Aynısını B için `dev/practice_b.py` ile (not tabanlı kapanış dahil).
2. `builder/` iskeleti: `build.py` (tek komut, 25 dk sınırı, temiz trace, export) ve kitaplığın kullanımını anlatan skill: builder ajanı brief'ten config çıkarır, `builder/lib` çağırır, `workflow.check` ve yerel snippet koşusunu trace'e yazar.
3. Gizli brief provası: test cevaplarına erişimi olmayan builder + ham malzeme biçiminde Brief A. Stil testleri (`--style pieces`, `in_words`).
4. Akşam: planı yeni yola göre sadeleştirmek.

- 2026-10-10: brief-a rebuilt from builder/work/brief-a/gen.py, saved (workflow c6a42d6d-1d07-45fc-b20a-e1397a49c55a, agent 9d00c85e-128a-463f-88a8-df1783a3f9b8, v2). run_cases blocked: practice server HTTP 500 on /v1/practice/sessions (3 tries).
