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
- **Planın geçersiz kısımları (20:05):** Yol B yüzünden planın §5–7, §9.1–9.5, §10.4'ün τ kısmı, §11.1–11.3, AgentSpec, iki sağlayıcı, V0/V1/V2 merdiveni, E1–E15 kuyruğu ve §16'daki Cuma/Day 1 checklist'lerinin çoğu kullanılmıyor. Geçerli olanlar: §2.5–2.8 (kurallar, kit olguları), §12.4 (Pazar takvimi), §13 (açık sorular), §14'ün workflow riskleri, §16 "Day 2 — kilitle ve teslim et".
- **Ölçüm kuralı (20:05):** gürültü (σ) bilinene kadar iki build toplam skorla değil, kalan vakaların geçme sayısıyla (ör. 1/3 → 3/3) karşılaştırılır.

## Açık sorular (destek kanalı)

19: ilk 10'un yeniden koşusunda builder'ın Claude anahtarını kim veriyor? · 23: gizli brief'lerin tool API'si pratik bankayla uyumlu mu, build sırasında test oturumu açılabiliyor mu? · 24: workflow sınırı 10 mu (site), 200 mü (kit README)?

## Kayıtlar

- Freya workflow'ları: `base` 0a1a92e1…, `brief-b` e6772bee… (agent 28027619…), `brief-a` 270d0e30… (agent 68a8b1f8…). Yerel eşleme: kit'te `.freya-agents.json`.
- Sonuçlar: kit'te `results/` (`base-A.json`, `b0-B-reps3.json`, `b0-A-reps3.json`, `b0-builder*.log`, `log.jsonl`). Trace'ler: `traces/` (anahtar içeriyor, paylaşılmaz).
- Commit edilmemiş: `builder/`, `tests/`, `dev/`, `pytest.ini`, `.gitignore` eki (`__pycache__/`, `.coverage`, `.pytest_cache/`, `dev/out/`). Testler: kökte `python -m pytest -q` (ağsız, ~6 sn).

## Sıradaki

Kural: aynı anda tek simülasyon; her ölçüm `--reps 3`; build `--cases` olmadan.

Yapıldı (21:17): A 8/10 → PUB-07/10 düzeltmesi; B ilk kez 2/3 → 3/3; ham malzeme A 9/10 (izolasyonlu). Ayrıntı son kayıtlarda.

1. **İzolasyonlu temiz B build'i:** `build.py brief-a.md brief-b.md openapi.json` → `--brief B --reps 3` (tarih kuralının skill katkısını kopyasız görmek için). İsteğe bağlı: yalnız A brief'iyle temiz build → `--brief A --reps 3`.
2. **PUB-06 kayması** ("what amount can you pay?"): tekrar ederse mekanizma ara (brief'in birebir yasak cümlesini görev mesajında öne almak gibi).
3. **`dev/replay.py`:** chat yolunda uydurma cevaplar; düzeltilmeden kullanma.
4. **Gece kuyruğu:** `--style pieces`, `--style in_words`, ikinci bir A build'i (build'den build'e σ); en sık hataya tek evrensel düzeltme.
5. **Pazar:** 16:00–18:00 temiz klon provası (A ve A+B, brief başına < 25 dk, trace içeriği, export, anahtar taraması); 19:00 kod dondurma; 20:00 gizli brief'ler; 23:00'ten önce form.
6. Düşük öncelik: destek kanalına 19, 23, 24; 1–2 kural mutasyonu.

- 2026-10-10: brief-a rebuilt from builder/work/brief-a/gen.py, saved (workflow c6a42d6d-1d07-45fc-b20a-e1397a49c55a, agent 9d00c85e-128a-463f-88a8-df1783a3f9b8, v2). run_cases blocked: practice server HTTP 500 on /v1/practice/sessions (3 tries).

## 10 Ekim, 18:50: Mac'e geçiş, temiz çalışma klasörü

Oturum İhsan'ın Mac'inde sürüyor (önceki koşular Windows'taydı). Python 3.14 (Homebrew); repo kökünde `.venv` açıldı (`claude-agent-sdk` 0.2.165, `pytest`), `.gitignore`'a eklendi. Testler venv'de: 429 yeşil. İnceleme bulgusu: 18:31 koşusu sıfırdan kurmadı; ajan önceki koşunun `builder/work/brief-a/gen.py`'sini bulup yeniden kullandı (trace'te yazıyor; dosyada Windows mutlak yolları var, Mac'te çalışmaz bile). Organizatör temiz klonda koşacağı için bu ölçümü şişirir. Düzeltme: `build.py` her koşuda dolu çalışma klasörünü ajanın okuyamadığı `dev/out/work-archive/<slot>-<zaman>/`'a taşıyor ve trace'e yazıyor; `.freya-agents.json` yerinde kalıyor (aynı workflow yerinde güncellenir). Ayrıca görüldü: üretilen `gen.py`'de `OUTCOME_EXTRACT` tanımlı ama hiçbir düğüme bağlı değil; sonuç ve nedeni yine çağrı bittikten sonra modelin doldurduğu alan belirliyor (PUB-05'in kaldığı yer). Ölçülmedi: Mac'te hiçbir build ya da simülasyon koşmadı; pratik sunucusunun 500'ü düzelip düzelmediği bilinmiyor.

**Karar (İhsan):** ölçüm döngüsü gizli brief koşulunda: builder `--cases` olmadan kurar, ölçüm ayrı `run_cases.py --reps 3` ile; önce A, sonra A+B. **Hesap değişimi:** İhsan kendi Freya hesabını kullanacak (takım arkadaşının workspace'i bırakıldı). Eski workspace'e bağlı üç durum dosyası silinmeden `dev/out/old-workspace/`'a taşındı: `builder/work/.freya-agents.json` (brief-a → c6a42d6d…), kit'in `.freya-agents.json`'u ve `.personas.json`'u (git'te takipli; `run_cases` personaları yeni workspace'te yeniden yaratıp dosyayı yeniden yazacak). Kit'teki `env.sh`'i (yeni `fak_` anahtarı) İhsan kendisi düzenliyor.

## 10 Ekim, 19:17–19:50: döngü 1 (gizli brief koşulu), A: 9/10

Yeni hesap ve workspace (İhsan). Build `--cases` olmadan, brief ve OpenAPI'den: 177 sn, $1,04, 14 tur; workflow `f2e31736…`, agent `f847f92e…` (v1), 6 düğüm, 10 tool, dry run geçti. Ölçüm `run_cases.py --brief A --reps 3`: **9/10** (koşular 9, 9, 9; 440 sn; en yavaş tur medyanı 10, 6, 7 sn; kapatan müşteri yok). Sonuçlar kit'te `results/c1-A-reps3.json`, çıktı `dev/out/c1-A-reps3.out`. Kalan tek vaka PUB-07, 3/3 aynı: müşteri tatil olan "Monday the 26th"i (son tarihten önce) söyleyince ajan "kaydedebileceğim en geç tarih 2 Kasım" dedi ve 2 Kasım'ı kaydetti; beklenen bir sonraki iş günü (27 Ekim). Kod gerçekleri doğruydu (takvimde 26 = X holiday, son tarih 2 Kasım); hata modelin üç gerçeği birleştirmesinde. Önceki Windows koşusunda (8/10) da aynı vaka kalmıştı.

Düzeltme (mekanizma, brief değeri yok): `calc.dates_code`'da adlandırılmış tarihe `"shifts": "forward" | "backward"`; runtime bugünden o tarihe kadar iş günü olmayan her günü yerine kullanılacak iş günüyle `bb_shifts__<ad>`'a ve tarih metnine yazıyor; ürün şablonuna `{deadline_shifts}` ve `{shifts:<ad>}`. Yön brief'ten config. Skill'e iki paragraf: tarih kararını model okusun, hesaplamasın (`shifts` + `{deadline_shifts}`); kapanış tool'unu çağrıdan sonra bir model dolduruyor, açıklamasında kapanış tablosunun tamamı "ne zaman" sütunuyla olmalı (kit builder'ı böyle yapıyor; bizim builder'ın açıklaması yalnız nedenleri sayıyordu; PUB-05 bu koşuda 3/3 geçti, satır ölçülmeden girdi). Testler: 432 yeşil (3 yeni).

## 10 Ekim, 19:30–20:05: döngü 2 (A: 7/10), ölçülmemiş düzeltmeler, durum değerlendirmesi

İlk `shifts` sürümüyle yeniden build (19:30, 150 sn, $0,86, 11 tur; aynı workflow `f2e31736…`, v2, 6 düğüm, 9 tool, dry run geçti). Ölçüm `--brief A --reps 3` (19:41): **7/10** (koşular 7, 9, 8; 419 sn). Kalanlar: PUB-05 1/3 (kapanış `not_reached/unclear`, beklenen `no_promise/hardship`), PUB-07 1/3 (yine 2 Kasım kaydedildi), PUB-10 1/3 (judge, başarılı yazmadan önce "recorded" sözcüğünü gördü; bir koşuda açılıştaki "This call is recorded" cümlesini saydı). Aynı v2'de yalnız PUB-07, reps 3 (19:55): 2/3. Sonuçlar kit'te `results/c2-A-reps3.json`, `results/c2-PUB07-reps3.json`, çıktı `dev/out/c2-A-reps3.out`. Okuma: c1 9/10 ile c2 7/10 iki ayrı build; build'den build'e ve koşudan koşuya oynama ±2 vaka, σ bilinmiyor.

Kodda, ölçülmemiş: (1) gün rehberi v2 (`runtime/dates.py` `shifts_text`): bugünden son tarihin bir hafta sonrasına kadar her gün için tek satır ("the 26th = …: holiday, not a business day -> use … instead", "AFTER the latest date"), ürün satırına `{deadline_shifts}`; (2) kapanışta `read_model`: modelin seçimini büyük/küçük harf, tek alana yazılmış iki değer, yalnız nedenle anılan sonuç gibi durumlarda toleranslı okur; `bb_close_model` artık modelin gönderdiğini ham yazar; (3) SKILL.md: tarih kararını model okusun, hesaplamasın; kapanış tool açıklamasında tablonun tamamı; `keep_model`'den sonra `var:bb_identity` kuralları (doğrulanmış müşteri `not_reached` ile kapanmaz); (4) `build.py`: girdiler çalışma klasöründe `inputs/`'a kopyalanıyor, kanca `dev/` ve `tests/`'i mutlak yolla da kesiyor (`tests/test_build_guard.py`); (5) `dev/replay.py`: bir pratik vakanın turlarını chat API'den gönderip ajanın cevaplarını basan karar anı testi (yalnız dev); (6) `dev/mutations/brief-a-raw.md`: Brief A ham malzeme biçiminde (e-posta, politika alıntısı, memo, kod listesi), koşulmadı. Testler: **457 yeşil**. Yerel `builder/work/brief-a/workflow.json` 19:57'de yeni kitaplıkla yeniden üretilmiş; platforma kaydedilip kaydedilmediği bilinmiyor, ölçülmedi.

Durum değerlendirmesi: en büyük boşluk Brief B. Finalde iki gizli brief'te de müşterilerin 1–3 ürünü var, bizim builder'la B hiç build edilmedi, ölçülmedi. Sonra ham malzeme biçimi, `--style` koşuları ve temiz klon provası. "Sıradaki" buna göre yeniden yazıldı; planın geçersiz kısımları "Kararlar"da.

## 10 Ekim, 20:10–21:00: döngü 3 (A: 8/10), PUB-07 ve PUB-10 kapandı (elle deneme), skill'e taşındı

`env.sh` artık yalnız komutun içinde `source` ediliyor (içerik basılmıyor; İhsan izin verdi). Build güncel kodla, `--cases` yok: 177 sn, $1,02, 16 tur. Eski workflow `f2e31736…` Freya'da yoktu (PUT → 404, panelden silinmiş olabilir); builder ajanı durum dosyasındaki kaydı kendisi silip yenisini yarattı: workflow `5ef7910f-e958-4c9f-84be-ddde326b0236`, agent `853f6728-5fcb-4d02-bb6d-e44e8b58bffb`, v2, 6 düğüm, 10 tool. Ölçüm `--brief A --reps 3`: **8/10** (koşular 8, 8, 8; 453 sn; en yavaş tur medyanı 9, 7, 6 sn). **PUB-05 3/3** (kapanış düzeltmesi tuttu). Kalanlar 0/3: PUB-07 ve PUB-10. Sonuçlar `results/c3-A-reps3.json`, `dev/out/c3-A-reps3.out`, build çıktısı `dev/out/build-a-run3.out`.

Teşhis (çağrı dökümleri ve `route_evaluated` değişken tablosu): PUB-07'de gün rehberi doğru ve ajanın önünde ("the 26th … holiday -> use Tuesday 27 October instead"), ama model "The latest date I can record is Monday 2 November" diyor: rehbere bakmadan son tarihten sonrası kuralını uyguluyor. Tarih kuralı tek paragraftı; kit ajanı aynı kuralı ayrı maddelerle yazıyor. PUB-10'da ajan dürüst (ilk deneme hatası söylendi, tekrar, sonra "recorded"); judge açılıştaki "This call is recorded" cümlesini "başarılı yazmadan önce 'recorded'" diye sayıyor. Kit ajanının açılışı "Please note that we record this call." (c1'de aynı açılışla PUB-10 3/3 geçmişti; judge tutarsız).

Elle deneme (aynı workflow, v3, `gen.py`'de iki değişiklik: tarih kuralı rehberin kendi sözcüklerine bağlı ayrı eğer-ise satırları, "latest date" cümlesi yalnız AFTER günü için; açılış "Please note that we record this call."): `--only PUB-07,PUB-10 --reps 3` → **PUB-07 3/3, PUB-10 3/3** (159 sn; `results/c3x-0710-reps3.json`). İkisi skill'e mekanizma olarak taşındı: tarih kuralının satır satır şablonu; "brief'in başarılı yazma sözcüğü yazma başarılı olmadan hiçbir turda geçmez, açılış dahil" kuralı (nötr örnekle). Skill'e taşınmış hali build'le **ölçülmedi** (B build'inin A koşusu ölçecek).

Bulgular: (1) Skill'deki gün rehberi örneği Brief A'nın tatil gününü ("26 October") taşıyordu; `test_no_brief_values` yalnız ISO tarihlere bakıyordu. Örnek nötr tarihle değişti, teste yazıyla tarih kontrolü eklendi (eski skill'i yakalıyor). (2) `builder/save.py`: durum dosyasındaki workflow Freya'da yoksa (404) yeniden yaratır; yeni yaratılan workflow'u bir kez daha kaydeder (kit ilk yaratmada ajan modelini ayarlamıyor, chat turu başlamayabiliyor); `tests/test_save.py`. (3) `dev/replay.py` güvenilmez: chat yolunda ajan tool çağırmadan cevap uyduruyor ("credit card", "1,240.50 euros", "social security number") ve turlar bir kayıyor (ilk cevap açılış). Düzeltilene kadar karar anı testi simülasyonla (`--only`) yapılıyor. Testler: **462 yeşil**.

## 10 Ekim, 20:31–20:46: döngü 4, Brief B ilk kez: 2/3 → elle deneme 3/3, skill'e taşındı

İlk B build'i (A+B girdisi, `--cases` yok): 119 sn, $0,73, 14 tur; workflow `1dfbdfd9-de27-40ef-a930-b76a416ec0a2`, agent `19e0b5d6-ed94-4936-9f56-57ae8f1b5415`, v1, 6 düğüm, 11 tool, dry run geçti. Builder skill'e yeni giren iki kuralı uyguladı (tarih eğer-ise satırları, "we record this call" açılışı). Ölçüm `--brief B --reps 3`: **2/3** (PUB-11 3/3, PUB-13 3/3 (kit ajanının kaldığı vaka), PUB-12 0/3; 212 sn; `results/c4-B-reps3.json`). PUB-12'de ledger doğru, judge kaldırıyor: ajan erken banttaki ürüne de iki deneme yapıyor (önceki ürünün desenini kopyalıyor), ürün satırında "No attempt 2 in this band" yazmasına rağmen.

Elle deneme, aynı workflow: (v3) bant `offers` metinleri açık durmayla bitiyor ("ONE attempt only: after attempt 1 is refused, stop for this product" / "After attempt 2 is refused, stop"), görev mesajına "her teklif bir deneme; o ürünün kendi satırındaki sayı, başka ürününki değil" → PUB-12 **2/3** (`results/c4x-12-reps3.json`); kalan koşuda ters hata: müşteri baştaki soruya "kişisel krediyi ve arabayı ödemiyorum" deyince ajan iki ürünü hiç denemeden not etti. (v4) "baştan reddedilen ürün de denemelerini alır, ilk mesajı attempt 1 teklifidir; denemeler bitmeden reddedildi diye kapatma" → **B 3/3** (PUB-11, 12, 13 hepsi 3/3; 185 sn; `results/c4y-B-reps3.json`). Mekanizma skill'e paragraf olarak taşındı (brief değeri yok; brief'in kendi sayma kuralı önceliklidir). Skill'e taşınmış hali **henüz ölçülmedi**; sıradaki: temiz build A+B → `--brief B` ve aynı ajanla `--brief A`, ikisi de `--reps 3`.

## 10 Ekim, 20:46–21:17: temiz build'ler, çalışma klasörü sızıntısı, ham malzeme brief'i (A: 9/10)

**Temiz B build'i (skill'deki deneme kuralıyla):** 121 sn, $0,75, 17 tur; aynı workflow `1dfbdfd9…`, v5. Builder skill'deki üç kuralı da uyguladı. Ölçüm: **B 3/3** (`results/c5-B-reps3.json`, 267 sn); aynı ajan `--brief A --reps 3`: **9/10** (PUB-07 3/3, PUB-10 3/3; PUB-05 1/3: tek ürünlü zor durumda `add_note` hardship yazıyor. Brief B kural 8'e göre bu doğru, Brief A ise "never uses add_note" diyor; yani B ajanını A vakalarıyla ölçünce PUB-05'in not kontrolü anlamsız. `results/c5-A-reps3.json`, 287 sn).

**Sızıntı bulgusu:** ham malzeme build'inin ilki 7 turda, 53 sn'de bitti; trace: builder `builder/work/brief-a/gen.py`'yi okuyup `sed` ile kopyalamış. Geriye bakınca iki B build'i de `builder/work/brief-a/gen.py`'yi okumuş; ikincisi (B 3/3'ü veren) benim elle tarih kuralı ve açılış eklediğim dosyayı. Yani c5'te tarih kuralı ve açılış için skill'in katkısı ayrılamıyor; deneme kuralı ise yalnız arşivlenmiş `brief-b` klasöründeydi, skill'den geldi. Organizatörün temiz klonunda `builder/work/` boş olacağı için bu, ölçümü şişirir. **Düzeltme:** `build.py` her koşuda `builder/work/` altındaki **bütün** slot klasörlerini (yalnız kendi slot'unu değil) okunamayan `dev/out/work-archive/`'a taşıyor; durum dosyası yerinde kalıyor.

**Ham malzeme brief'i, temiz izolasyonla** (`dev/mutations/brief-a-raw.md`: e-posta + politika alıntısı + memo + kod listesi): build 200 sn, $1,02, 18 tur; workflow `3b9c4693-986c-41c4-b8ca-9c5db791b55e`, agent `e450b416-fbec-4e98-b435-18a59cda9249`, v3, 6 düğüm, 9 tool. Memo doğru uygulandı (erken bant 12. iş günü, kodda "C7 + MEMO 1"). Ölçüm `--brief A --reps 3`: **9/10** (koşular 10, 9, 10; 775 sn; 3. koşu 513 sn, model yavaştı). PUB-05, 07, 10 3/3: tarih kuralı ve açılış skill'den, kopyasız tutuyor. Kalan PUB-06 2/3: bir koşuda "what amount can you pay?" diye sordu (brief yasaklıyor; tek seferlik model kayması). Sonuçlar `results/c6-raw-A-reps3.json`, `dev/out/c6-raw-A-reps3.out`, build `dev/out/build-raw-run2.out`.

Durum (21:17): yalnız A brief'iyle izolasyonlu temiz build ölçülmedi; ham malzeme A-eşdeğeri olarak 9/10 veriyor. B 3/3 (deneme kuralı skill'den; tarih kuralının kaynağı karışık). Sıradaki: izolasyonlu temiz B build'i (B ve A), sonra gece kuyruğu (`--style pieces`, `in_words`).

## 10 Ekim, 21:18–21:45: izolasyonlu temiz B build'i (B: 1/3), çağrı sonu sırası

İzolasyonlu temiz build (A+B, bütün çalışma klasörleri arşivde; trace'te başka slot okuması yok): 205 sn, $0,95, 15 tur; aynı workflow `1dfbdfd9…`, v6, 6 düğüm, 10 tool. Skill'deki üç kural kopyasız uygulandı (açılış kendi sözleriyle: "…and we record this call."). Ölçüm `--brief B --reps 3`: **1/3** (PUB-11 3/3, PUB-12 2/3, PUB-13 2/3; 770 sn, model yavaş; `results/c7-B-reps3.json`). Yani 20:53'teki B 3/3 kopyalı build'in sonucuydu, şişkindi.

Teşhis (döküm + olaylar): iki kalma da çağrının sonundaki çok adımlı sırada. PUB-13: müşteri ikinci ürünün tarihini kabul ediyor, ajan hiçbir şey söylemeden `end_call` çağırıyor (geri okuma, `create_promise`, veda yok) → `no_promise/refused`. PUB-12: söz kaydediliyor, `create_promise` sonucunun mesajı "müşteriye söyle … sonra add_note" sırasında; ajan söyleyip vedalaşıyor, `add_note` hiç çağrılmıyor. Notları erken yazmak çözüm değil: Brief B kural 10, devirde hiç not istemiyor.

Mekanizma (ölçülmedi): runtime post-kanca mesajına `{open:<tool>:<tool>...}` yer tutucusu: `bb_products` sırasıyla, listelenen tool'ların hiçbirinin henüz yazmadığı ürünler ya da "none" (`runtime/hooks.py` `open_items`, test eklendi). Skill: çağrı sonuna gelebilecek her mesajda önce kalan tool çağrıları, en son müşteriye söylenecekler; kalan ürünler `{open:…}` ile adıyla; `end_call` açıklaması "yalnız kapanış cümlesinden sonra, okunmamış/kaydedilmemiş söz ya da eksik kayıt varken asla". Testler: **463 yeşil**.

## 10 Ekim, 21:58–22:10: B ajanı A'da 7/10, salt-okuma denetimi, teslim düzeltmeleri

İzolasyonlu B ajanı (v6) `--brief A --reps 3`: **7/10** (1354 sn, model çok yavaş: tekrar başına ~7,5 dk; `results/c7-A-reps3.json`). PUB-05 0/3 ve PUB-08 1/3 yalnız `add_note` yüzünden (B kuralı 8, A'da not yok; B ajanında beklenen), PUB-06 2/3 (taban teklifi iki kez yapıldı; ham malzeme build'inde de bu vakada 1 koşu kalmıştı, izleniyor). PUB-07 ve PUB-10 3/3: tarih kuralı ve açılış izolasyonlu build'de skill'den tutuyor.

Yeni skill'le (çağrı sonu sırası, `{open:…}`) izolasyonlu B build'i: 206 sn, $0,99, 14 tur, v8, 11 tool; `{open:` gen.py'de kullanıldı. Ölçümü koşuyor.

Salt-okuma denetimi (Workflow: 2 denetçi + bulgu başına bir çürütücü, 18 ajan): 16 bulgudan 15'i doğrulandı, çoğunun önemi düşürüldü. Hemen düzeltilenler: (1) `requirements.txt` (`claude-agent-sdk==0.2.165`, pytest) ve kök `README.md` (temiz klonda kurulum ve komut); (2) PreToolUse kancası yalnız komut, yol ve arama desenlerine bakıyor, yazılan dosya içeriğine değil (önce "environment", "results/" geçen notları ve gen.py'yi reddedebiliyordu); red nedeni eşleşen parçayı söylüyor; (3) export yalnız bu koşunun kaydettiğini yazıyor (durum girdisi değişmediyse dosya yazılmaz, çıkış 1); export hatası yakalanıyor, `[end]` satırı her durumda yazılıyor. Testler: **465 yeşil**.

Açık kalan denetim bulguları (orta): hook ve close-hook ayarları OpenAPI işlemine karşı denetlenmiyor (gizli API'de alan ya da enum adı değişirse sessiz bozulma); aynı dosya adlı iki gizli brief aynı slot'a düşer (ikinci build birinciyi ezer); ürün modeli hesaplanan taban (yüzde vb.) ve türe göre bant ifade edemiyor. Düşük: rakamsal `digits` normalizasyonu harfli cevapları bozabilir; gün rehberinde ay atlayınca "the 14th" iki kez geçer; tarih korumasının alt sınırı yalnız "today"; "this <weekday>" anlamı sabit; trace her model çağrısını ayrı satırda yazmıyor; trace'ler gitignore'da (teslimde ayrıca kopyalanmalı); `submission/`'da pratik export'ları teslimden önce temizlenmeli.

## 10 Ekim, 22:02–22:13: izolasyonlu B build'i, çağrı sonu mekanizmasıyla: B 3/3

Yeni skill'le (çağrı sonu sırası, `{open:…}`, `end_call` açıklaması) izolasyonlu temiz build: 206 sn, $0,99, 14 tur, v8, 11 tool. Ölçüm `--brief B --reps 3`: **3/3** (koşular 3, 3, 3; 673 sn; `results/c8-B-reps3.json`). Önceki izolasyonlu sonuç 1/3'tü (PUB-12 notlar atlanıyor, PUB-13 söz kaydedilmeden kapanıyor); ikisi de kapandı. Bu, kopyasız ilk B 3/3.

Bu arada (ölçülmedi, builder davranışını etkileyebilir): `op=` ile hook ve kapanış alan denetimi, kancanın yalnız komut ve yollara bakması, export'un yalnız bu koşunun kaydını yazması, slot'a girdi özeti. Sıradaki: en güncel kodla izolasyonlu yalnız-A build'i → `--brief A --reps 3`.

## 10 Ekim, 22:14–22:28: izolasyonlu yalnız-A build'i, en güncel kodla: A 10/10

Build (yalnız brief-a, bütün çalışma klasörleri arşivde, `op=` denetimi, dar kanca): 183 sn, $0,98, 16 tur; workflow `5ef7910f…`, agent `853f6728…`, v5, 6 düğüm, 9 tool; gen.py'de 9 `op=ops[…]`. Ölçüm `--brief A --reps 3`: **10/10** (koşular 10, 10, 10; 655 sn; `results/c9-A-reps3.json`). Kopyasız ilk A tam puanı; kit builder'ının B0 10/10'u test setini görerek kurulmuştu.

Özet (22:28), hepsi izolasyonlu temiz build, `--reps 3`: **A 10/10, B 3/3, ham malzeme A 9/10** (PUB-06 2/3). Kuyruk (`dev/out/queue.log`, betik scratchpad'de): Brief C ve Brief D (repo kökünde, A'nın kural değiştirilmiş, tek başına verilen kopyaları: C insan isteğinde 4. talepte devir ve devir duyurusu; D on iki konuşma kuralı) build + A vakaları; sonra `--style pieces`/`in_words` (A), `--style pieces` (B), ikinci B build'i. Not: A vakaları C ve D'nin yeni kurallarını sınamıyor (insan isteyen müşteri yok); o kurallar için kendi vaka dosyamız gerekir.
