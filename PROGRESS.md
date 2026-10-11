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
- **Builder effort'u max (11 Ekim 03:25, İhsan):** aynı vakalarda koşu bazında max 50/54, medium (varsayılan) 46/54 (B 7/9–7/9, I 15/15–12/15, A 28/30–27/30); build ~4–6 dk ve ~$1,5 (medium ~3 dk, ~$1,0). `build.py`'de varsayılan, `BUILDER_EFFORT` ile değiştirilebilir.
- **Ölçüm kuralı (20:05):** gürültü (σ) bilinene kadar iki build toplam skorla değil, kalan vakaların geçme sayısıyla (ör. 1/3 → 3/3) karşılaştırılır.

## Açık sorular (destek kanalı)

19: ilk 10'un yeniden koşusunda builder'ın Claude anahtarını kim veriyor? · 23: gizli brief'lerin tool API'si pratik bankayla uyumlu mu, build sırasında test oturumu açılabiliyor mu? · 24: workflow sınırı 10 mu (site), 200 mü (kit README)?

## Kayıtlar

- Freya workflow'ları: `base` 0a1a92e1…, `brief-b` e6772bee… (agent 28027619…), `brief-a` 270d0e30… (agent 68a8b1f8…). Yerel eşleme: kit'te `.freya-agents.json`.
- Sonuçlar: kit'te `results/` (`base-A.json`, `b0-B-reps3.json`, `b0-A-reps3.json`, `b0-builder*.log`, `log.jsonl`). Trace'ler: `traces/` (anahtar içeriyor, paylaşılmaz).
- Commit edilmemiş: `builder/`, `tests/`, `dev/`, `pytest.ini`, `.gitignore` eki (`__pycache__/`, `.coverage`, `.pytest_cache/`, `dev/out/`). Testler: kökte `python -m pytest -q` (ağsız, ~6 sn).

## Sıradaki

Kural: aynı anda tek simülasyon; her ölçüm `--reps 3`; build `--cases` olmadan. Gizli brief'ler 20:00, teslim 23:00.

**Durma kuralı (11 Ekim 09:50, önerildi):** 12:30'da ajan davranışı (skill, prompt, runtime) donar; sonrası yalnız çökme düzeltmesi. "Yeterince iyi": organizatör A ≥ 9/10, B ≥ 2/3, kendi vakalarda sabah tabanına göre gerileme yok (hepsi `--reps 3`); bunu sağlayan en iyi sürümle gidilir.

1. **12:30 donuldu** (`4f64795` skill'i; A v23 10/10, B v18 8/8). Genelleme kuyruğu `queue16`: ham A, I, G, H, C, D; E ve F yalnız build (~15:00). Sonra pratik workflow'lar panelden silinir.
2. **10:40–12:30:** yalnız ölçümle kanıtlanmış hata. Tek yapısal istisna: B'de kapı yine model `end_call`'u yüzünden delinirse end_call aracı hiçbir adımda olmaz, bitişler rotayla `end_call` düğümüne.
3. **12:30–16:00:** donmuş sürümle tam ölçüm (A, B, own-a-1/2, own-b-1/2, ham malzeme A, I).
4. **16:00–18:00:** temiz klon provası `ANTHROPIC_API_KEY` ile, `python3 builder/build.py` (venv'siz kabuk), trace `submission/<slot>.trace.log`, export, `fak_`/`sk-ant` taraması.
5. **19:00** kod dondurma, etiketli commit; **20:00** gizli brief'ler: `python3 builder/build.py <brief> <api> 2>&1 | tee traces/hidden-N.log`; **23:00'ten önce** form (team, repo, commit, run_command, workflows, traces).
6. Açık sorular: destek kanalına 19, 23, 24 (workspace'te 11 workflow görüldü; sınır 10 değil gibi).

- 2026-10-10: brief-a rebuilt from builder/work/brief-a/gen.py, saved (workflow c6a42d6d-1d07-45fc-b20a-e1397a49c55a, agent 9d00c85e-128a-463f-88a8-df1783a3f9b8, v2). run_cases blocked: practice server HTTP 500 on /v1/practice/sessions (3 tries).

## Dondurma durumu ve açık ajan zayıflıkları (11 Ekim 12:30, `freeze-1230`, skill `4f64795`)

Eski (A v22 / B v17) ve yeni (A v23 / B v18) sürüm, hepsi `--reps 3`:

| Vaka dosyası | Eski sürüm | Yeni sürüm |
|---|---|---|
| Organizatör A | 9/10 (29/30) | **10/10** (30/30) |
| own-a-1 | 7/10 (21/30) | 7/10 (24/30) |
| own-a-2 | 10/10 | 10/10 |
| Organizatör B | 2/3 (8/9) | 8/8 çağrı (1 çağrı kesintide kayıp) |
| own-b-1 | 1/3 (7/9) | 1/3 (7/9) |
| own-b-2 | 3/3 (9/9) | 2/3 (7/9), biraz düştü |

Düzeltilen PUB-09 (geri arama alınmadan "geri arama alındı" yazılması) artık 3/3. own-b-2'deki düşüş tarih hatası: müşteri "bu Cumartesi" (17 Ekim) dedi; Brief A kural 19–20'ye göre ajan bir sonraki iş günü Pazartesi 19'u önerir, müşteri kart ve araba kredisi için kabul etti. Ajan kartı 19'a doğru, araba kredisini 16 Ekim Cuma'ya (kendi 1. deneme teklif tarihi, müşterinin kabul etmediği) kaydetti. Değişiklik yalnız kapanış korumasına dokunuyor, tarih hesabına değil; aynı skill'le kurulan iki build arasındaki oynama. Durma kuralı (A ≥ 9/10, B ≥ 2/3, gerileme yok) sağlandı.

Açık zayıflıklar (kodda mekanizması yok, model kuralı bazen atlıyor):
- birden çok üründe tarih karışması (bir ürünün tarihi başka üründen ya da konuşmadaki başka bir tekliften alınıyor);
- ürün başına deneme sayısı (geç banttaki ürüne 2. deneme yapılmıyor ya da erken banttakine fazla);
- "iki kez konuşmak istemiyorum" diyen müşteriyle görüşmeyi sürdürmek (own-a-1 PUB-05, 0/3);
- bir koşuda servis hatasından sonra kaydı tekrar denememek (own-a-1 PUB-10, 1 koşu).

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

## 10 Ekim, 22:35: Brief C ve D (τ-bench kaynaklı mutasyonlar)

`dev/mutations/brief-c.md` ve `brief-d.md` (İhsan): τ-bench (Sierra, hyper-tau-bench, commit `6e9f34c`) bankacılık politikalarından seçilip bizim senaryomuza uyarlanmış, Brief A tabanlı, tek başına verilen brief'ler. C: insan isteği için konuşma boyunca sayılan dördüncü talepte `general` devri, desteklenmeyen istekte devir teklifi, her başarılı devirden sonra birebir duyuru cümlesi; insan isteği ret ya da kimlik reddi sayılmaz. D: on iki adlandırılmış konuşma kuralı (tek görünür eylem, "unfortunately" ve "I can't" yasağı, en çok bir özür, sonuç bildirmeden önce doğrulama, genel yardım daveti yok vb.) ve bunların zorunlu cümlelerle ilişkisi. Kuyrukta A vakalarıyla ölçülüyorlar (A vakalarında insan isteyen müşteri yok; yeni kuralları ayrıca sınamak için kendi vaka dosyamız gerekir).

Kendi vaka dosyaları (22:45, `dev/cases/`, builder okuyamaz): müşteri verisi pratik vaka kimliğinden (bankada kimliğe bağlı, `PUB-10`'un enjekte hatası dahil), senaryo, beklenen kayıt ve kontroller bizim. `brief-c-cases.json` (PUB-01: dört kez insan isteği → 4.'de `general` devri ve birebir duyuru; PUB-09: yeniden yapılandırma devri + duyuru; PUB-06: desteklenmeyen soru (faiz oranı) → uydurma yok, insan teklifi, kabul → `transferred/human`), `brief-c-cases-2.json` (PUB-01: iki insan isteği sonra bugün tam ödeme; devir olmamalı; aynı kimlik bir dosyada iki kez olamadığı için ayrı), `brief-d-cases.json` (PUB-10, 05, 03, 06 senaryoları + D'nin yasak kelime, tek özür, genel yardım daveti yok, hatayı iç ayrıntısız açıklama kontrolleri). Kuyruk (`queue2.sh`): D build + A vakaları, C ve D kendi vakaları, stil koşuları, ikinci B build'i.

## 10 Ekim, 22:29–23:15: Brief C (A vakaları: koşuların %90'ı), bankada kesinti, kapanış tekrarı

Brief C build'i: 168 sn, $0,85, 13 tur; workflow `9d066d1f-d0fc-4e2c-a80d-87b4b99a991c`, agent `049521c6-68f6-4668-829f-97628b02540f`, 6 düğüm, 9 tool. A vakalarıyla 3 tekrar: koşular **7, 10, 10** (27/30); pass^3 ile 7/10. 3. tekrarın çıktısı kuyruğu yeniden kurarken kesilen süreçle kayboldu; Freya'daki çağrılar ve bankanın kayıtları üzerinden salt okuma yeniden puanlandı (10/10). 1. tekrarın üç kalması (PUB-02, 08, 09) altyapıdan: bankanın sahte sunucusu bir süre JSON yerine HTML hata sayfası döndürdü; `close_call` (PUB-08, 09) ve `schedule_callback`/devir (PUB-02, 09) bu hatayla düştü. Ajanın davranışı doğruydu.

Ders ve düzeltme: kapanış tool'u çağrıdan sonra bir kez koşuyor; kısa bir banka kesintisi vakayı düşürüyor. `tools.api_tool` artık yaşam döngüsü tool'larında varsayılan `maxRetries: 2` veriyor (normal tool'larda 0 kalıyor; brief'in tekrar kuralı geçerli). Banka 500'ü "hiçbir şey kaydedilmedi, tekrar edilebilir" diye tanımlıyor; `close_call`'dan sonraki çağrı kabul edilmiyor, çift kapanış riski yok. Test eklendi, **468 yeşil**. Ölçülmedi.

C'nin insan sayacı: builder "konuşma boyunca insan isteklerini say" kuralını system prompt'ta modele bıraktı (deterministik sayaç yok). Kendi vakalarımız (`dev/cases/brief-c-cases*.json`) kuyrukta ölçecek.

Brief D build'i: 629 sn (ajan süresi 626 sn; model yavaştı), $0,95, 18 tur; workflow `ee96c670-025f-4d40-b8d6-796e18abb44b`, agent `29f8eaaf-2a44-45e8-bc18-c416ee902767`. A vakalarıyla ölçümü koşuyor.

## 10 Ekim, 23:04–00:00: Brief D (A vakaları, 1. tekrar 7/10), takılan simülasyon, iki skill dersi

D ölçümünün 1. tekrarı (`b50e64e5`): 10 çağrının hepsi 23:08'de bitti ve sonuçlandı, ama simülasyonun durumu "running"de kaldı; `run_cases.py` 44 dk bekledi. Kit belgelerinde simülasyonu durduran çağrı yok (README yalnız "çağrı hiç başlamazsa running'de kalır" vakasını anlatıyor). Sonuç Freya ve ledger'dan salt okuma yeniden puanlandı: **7/10**. Bekleyen süreç durduruldu; İhsan'dan takılan simülasyonu panelden silmesi istendi (aynı anda tek simülasyon kuralı yüzünden kuyruk ondan sonra başlayabilir). D'nin A vakalarındaki 2. ve 3. tekrarı yok; D yeniden kurulunca tam ölçülecek.

D'nin üç kalması: PUB-07 hakem gürültüsü ("All criteria met" yazıp `inconclusive` verdi). PUB-05 gerçek: işini kaybeden müşteriye iki ikna denemesi ve taban teklifi (D'nin "sıkıntıyı kısaca kabul et, sonra somut sonraki adım ver" üslup kuralı, zor durumda ikna yasağını ezdi). PUB-10 gerçek: `create_promise` ilk hatasında tekrar yok, `no_promise/service_error` (builder D'nin "önce müşteriye açıkla, sonra tekrar dene" cümlesini retry mesajına "müşteriye söyle …, sonra tekrar çağır" sırasıyla yazdı; model konuşup turu bitirdi, tekrarı unuttu).

Skill'e iki mekanizma (ölçülmedi): (1) her "retry" mesajında tekrar çağrı aynı turda ve önce; müşteriye söylenecek kısa cümle çağrıyla birlikte (B'nin çağrı sonu dersinin genellemesi); (2) üslup kuralı ile bir durumda bir eylemi yasaklayan kural çatışırsa yasaklayan kazanır; görev mesajında yasaklayan kuralın yanına yazılır. Testler: 468 yeşil.

## 11 Ekim, 00:02: Brief C kendi vakaları: 2/3 (8/9 koşu)

C ajanı (`049521c6…`) `dev/cases/brief-c-cases.json`, `--reps 3`: **2/3** (koşular 3, 2, 3; 477 sn; `dev/out/q-C-own-reps3.out`). PUB-01 "dört kez insan" **3/3**: ilk üç talepte devir yok, 4.'de `general` devri ve duyuru (builder sayacı system prompt'ta modele bırakmıştı; bu senaryoda doğru saydı). PUB-06 "faiz oranı" **3/3**: uydurma yok, insan teklifi, kabulde devir. PUB-09 "yeniden yapılandırma + duyuru" **2/3**: kalan koşuda model `transfer_to_agent` ile `end_call`'ı aynı turda çağırdı; çağrı kapandı, duyuru kapanıştan sonra kaldı; ayrıca söylenen cümlenin sonunda `<">` artığı vardı (post-kanca mesajında `\"` ile tırnaklanmış birebir cümleyi model kaçış karakteriyle kopyaladı). İki olası mekanizma (yapılmadı): birebir cümleleri mesajlarda tırnaksız ayrı satırda vermek; `end_call` açıklamasını "başka bir tool'la aynı turda asla" diye sıkılaştırmak.

İkinci C dosyası (iki insan isteği sonra ödeme) ve D'nin yeni skill'le yeniden build'i kuyrukta (`queue3.sh`; D önce).

## 11 Ekim, 00:02–00:10: Brief D v2 ve yeniden build

Kökteki `brief-d.md` 23:49'da Codex tarafından güncellenmiş (14,9 KB → 17,5 KB): kural 37 (ilk hatadan sonra tekrar onay istemeden bir kez daha dene, en çok iki `create_promise`), kural 32 (zor durumda ek teklif yok), kural 30/31 (deneme sayımı), 42/15 (insan isteği ret sayılmaz) netleştirildi; "48–59 yalnız ifadeyi sınırlar, 1–47'yi değiştirmez" öncelik paragrafı eklendi. Yani v2, ilk D ölçümünde bulunan iki gerçek hatanın (PUB-05, PUB-10) konusunu brief'te çözüyor. `dev/mutations/brief-d-v2.md` olarak saklandı; `brief-d.md` (v1, belirsiz hali) duruyor. Girdi değiştiği için slot koruması yeni slot açtı: `brief-d-518c5c` (workflow `6c07ec04-0b22-4c33-ae99-0dd2746ec093`, agent `41001003-4faf-421f-bb87-7f1002e8a258`, v2; build 190 sn, $1,04, 15 tur; build retry ve "yasaklayan kural kazanır" skill kurallarıyla, `end_call`/birebir cümle kuralından önce). Not: v2 sonucu, skill düzeltmesinin katkısını brief'in netleştirmesinden ayırmaz; v1'in yeni skill'le ölçümü bunu ayırır.

## 11 Ekim, 00:17: Brief D v2, A vakaları: 10/10

D v2 ajanı (`41001003…`, yeni skill: aynı turda retry, yasaklayan kural kazanır) `--brief A --reps 3`: **10/10** (koşular 10, 10, 10; 636 sn; `dev/out/q-D2-A-reps3.out`). İlk D build'inin 1. tekrarındaki PUB-05 (zor durumda teklif) ve PUB-10 (retry yok) kapandı. Katkı ayrılamıyor: brief v2 bu iki konuyu netleştirdi, skill de değişti. Ayırmak için D v1'in yeni skill'le ölçümü kuyrukta.

## 11 Ekim, 00:17–00:50: stil testi `pieces` (A), iki tur

İlk tur (A ajanı v5, eski skill): 1. tekrar 8/10, 2. tekrar 9/10 (simülasyon "running"de takıldı, `dev/rescore.py` ile puanlandı; 3. tekrar koşulmadı). Bulgular: (1) kimlik adımının girişi `wf.llm` ile üretiliyordu; model brief'te olmayan "ilk evcil hayvanınızın adı" sorusunu uydurdu; (2) "14 March" + "1988" iki turda gelince ajan birleştirmedi, altı kez tam tarihi istedi, doğrulanamadı diye kapattı; (3) PUB-03'te müşteri modeli parçaları karıştırıp gerçek tarihi söyledi (test artığı, ajan doğru). Skill: sabit `wf.say` girişleri; parça parça cevabı birleştirme kuralı.

İkinci tur (A v7, yeni skill; build 236 sn, $1,13): `--style pieces --reps 3` **7/10** (koşular 9, 9, 8; 26/30; `dev/out/q-A5-pieces-reps3.out`). PUB-01 ve PUB-03 3/3 (kimlik düzeldi). Kalanlar tutarda: PUB-07 500 ve 180 (beklenen 540), PUB-04 400 (beklenen 1250), PUB-06 taban iki kez. Kök neden: ajan tarih anlaşıldıktan sonra tutarı **soruyor** ("how much of the 540.00 will you be paying?"), brief kural 24 yasaklıyor; parça parça konuşan müşteri ilk parçayı söylüyor ("Twelve", "5"). Skill: yasak yerine söylenecek cümle (tarih anlaşılınca "Can you pay the full past-due amount of <amount> on <date>?"), sayı parçaları da birleştirilir. A yeniden build ediliyor, `pieces` yeniden ölçülecek.

Takılan simülasyonlar: hakemin `inconclusive` verdiği çağrı olunca simülasyon "running"de kalıyor (iki kez; `maxRetries: 3`). `dev/rescore.py <sim>` takılan simülasyonu Freya çağrıları ve ledger'dan puanlıyor; simülasyon panelden silinmeden yenisi başlamıyor.

## 11 Ekim, 00:46–01:05: `pieces` üçüncü tur (tutar düzeltmesiyle): 6/10, 26/30

A v9 (build 198 sn, $1,16; görev mesajında "Right after a date is agreed and no amount yet: ask 'Can you pay the full past-due amount of <full amount> on <date>?'"). `--style pieces --reps 3`: **6/10** (koşular 9, 8, 9; 26/30; 3. koşu yavaş, en yavaş tur medyanı 11 sn; `dev/out/q-A6-pieces-reps3.out`). Tutar sorunu kapandı (PUB-04, PUB-06 3/3; PUB-07'de tutar doğru). Kalan dört kalma dört ayrı vakada, her biri bir koşu: PUB-10 (yavaş koşuda retry mesajına uyulmadı; mesaj doğru yazılmıştı), PUB-07 (tatilde son tarih önerildi, kesin gün iki kez soruldu), PUB-02 ve PUB-03 (müşteri kapattı). Okuma: parçalı konuşmada tur başına 1–2 dağınık kalma; vaka bazlı düzeltme genellemeyi riske atar.

Deney adayı (yapılmadı): yazma tool'unun tekrarını platforma devretmek (`maxRetries` = brief'in tekrar sayısı, hook `retries=0`); platformun 500'de tekrar edip etmediği belgede yok, PUB-10 `--only` ile sınanabilir. `in_words` koşuyor.

## 11 Ekim, 00:59–01:20: `in_words` (A) 8/10, post-kanca hatada çalışmıyor, platform tekrarı denemesi

A v9 `--style in_words --reps 3`: **8/10** (koşular 8, 9, 9; 26/30; 770 sn; `dev/out/q-A6-inwords-reps3.out`). PUB-06 2/3 (bir koşuda "How much can you pay, and on what date?"). **PUB-10 0/3**: banka hatası (500, "service unavailable, nothing was recorded") Freya'da `function_call_error` olarak geliyor ve **post-kanca çalışmıyor**; model ham hatayı görüp vedalaşıyor, retry yok. Akşam (22:17, A v5) aynı vaka 3/3 geçmişti; platform ya da banka davranışı değişmiş olabilir, bilinmiyor.

Deney (`exp-retry` slot'u, workflow `bb579de0-5707-4364-96d2-35d7eb04ca2d`, A v9 + `create_promise` `maxRetries: 1`, hook retries 0): `--only PUB-10 --reps 3` 2/3; olaylarda platform tekrarı yok (`function_call_start` → `function_call_error` → model konuşuyor); geçen iki koşuda ikinci çağrıyı model bir sonraki turda kendi yaptı. Sonuç: `maxRetries` bu banka hatasında tekrar etmiyor; yaşam döngüsü tool'larının varsayılan `maxRetries: 2`'si de kesintiye karşı koruma sayılmamalı (docstring düzeltildi). Skill: system prompt'a "tool hata döndürür ve what_to_do_next yoksa çağrı başarısızdır; brief'in o tool için başarısızlık kuralını uygula (çoğunlukla aynı turda aynı değerlerle bir kez daha)". A yeniden build edilip normal A ile ölçülüyor. Not: `exp-retry` workflow'u workspace'te bir yer tutuyor (7/10); panelden silinebilir.

Repo kökünde yeni dosyalar: `brief-e.md` … `brief-h.md` ve bir plan dosyası (kim eklediği soruldu).

## 11 Ekim, 01:16–01:28: A v11 (hata yedeği kuralıyla): 10/10

Build 194 sn, $0,99, 18 tur; v11; system prompt'ta "If a tool call returns an error and no what_to_do_next, that call failed …: call it once more with the same values, in the same turn". `--brief A --reps 3`: **10/10** (koşular 10, 10, 10; 480 sn; `dev/out/q-A7-reps3.out`). PUB-10 3/3. Gecenin bütün skill değişiklikleri (sabit giriş, parçalı cevap, tutar önerme, retry) A'da gerileme yapmadı.

`dev/mutations/brief-e.md` … `brief-h.md` (Codex, 00:52, kökten kopya): E tek ürün + eyleme özel onay (özellikle geri arama), F tek ürün + ek belge yok / iç bilgi açıklanmaz, G 1–3 ürün + C'nin insan sayacı, H 1–3 ürün + D'nin konuşma kuralları. Sıradaki: G ve H build + `--brief B --reps 3`.

## 11 Ekim, 01:28–01:45: Brief G (B vakaları 1/3), döngü hatası, aşırı uyum denetimi ve genelleştirme

G build'i (1–3 ürün + C'nin insan sayacı): 201 sn, $1,06, 18 tur; workflow `2879165a-7e6c-4f0b-8905-c381ff2f857f`, agent `1232dcdb-23f5-4adb-941c-3e07e8519424`. `--brief B --reps 3`: **1/3** (koşular 2, 1, 3; PUB-13 3/3, PUB-11 2/3, PUB-12 1/3; `dev/out/q-G-B-reps3.out`). PUB-12'de **döngü**: müşteri "kredi kartını yarın öderim" dedikçe ajan 70 kez "Can you pay the full past-due amount of … on …?" diye sordu (160 mesaj, müşteri kapattı). Kaynak: 00:45'te skill'e eklenen "tarih anlaşılınca birebir tam tutar sorusu" kuralı; A'daki tutar hatasını kapatırken B'de katı bir döngü yarattı. PUB-11'de borç bildirimi `wf.llm` ile üretildi, ürünler tutarsız ve gün sayısız sayıldı.

Aşırı uyum denetimi (Workflow: 3 mercek, test seti sızıntısı / pratik yapı varsayımı / düzeltmelerin kaynağı; bulgu başına çürütücü; 31 ajan): 19 bulgu doğrulandı, 9 çürütüldü. Düzeltilenler:
- Skill'de pratik vaka verisi vardı: PUB-01'in doğum tarihi ve telefon haneleri, PUB-07'nin tutarı ve cevabı ("540.00", "five hundred"), kitaplık açıklamalarında "4821", ilk "nötr" seçimde de bir pratik doğum yılı (1979). Hepsi pratik veriye karşı kontrol edilmiş nötr değerlerle ya da yer tutucuyla değişti. `test_no_brief_values.py` artık test setinin adlarını, kimlik cevaplarını (ISO, "D Month", "Month D", DD/MM/YYYY, yıl), kart hanelerini ve tutarlarını da arıyor.
- Builder erişimi: Read/Grep/Glob yalnız `builder/`, kit `docs/` ve `tools/`, `freya.py` altında; yolsuz arama ve kökten özyinelemeli arama reddediliyor; Bash'te `submission/`, `briefs/`, `out/`, `examples/`, `mutations/`, `PROGRESS`, plan dosyaları, `.personas`, kökteki `brief-*.md` engelli (önce bunların hepsi okunabiliyordu; trace'lerde kullanım görülmedi). 23 yeni guard testi.
- Skill genelleştirildi: altı düğümlü düzen "bu akışa sahip brief için varsayılan", adımlara brief'in izin verdiği tool'lar; kimlik girişi brief'in soru sayısı ve sırasıyla; kitaplık özetinde pratik değerler yerine yer tutucu (WORKDAYS, ORDER, N, SHIFT, inclusive, band_field, default_type); deneme sayma koşul-önce (brief'in kendi sayma kuralı if-then); kapanışta kimlik kuralları brief tablosunun koşullarından; çağrı sonu `{open:…}` brief'in ürünü tamamlayan yazmalarıyla; hata yedeği "bir kez daha" varsayımı yok, brief'in her tool için kuralı adıyla; tutar: her durum için brief'in sonraki teklif cümlesi, "tarih söyleyip daha düşük tutar demeyen müşteri teklif edilen tutarı kabul etmiştir: geri okumaya geç", "aynı soruyu üçüncü kez sorma".
- Kitaplık: `products_code(say_line=…)` her ürün için bir cümle `{{debt_statement}}`'e yazıyor (borç bildirimi `wf.say` ile, ürün atlanamaz).
Testler **505 yeşil**. Ölçülmedi; H build'i ve G'nin yeniden build'i bu skill'le yapılacak. Açık denetim bulgusu: mutasyon brief'lerinin hepsi A'nın 1–47 kuralını taşıyor; A'ya aşırı uyumu ölçmek için gerçekten farklı bir brief gerekli (soru sırası, önceki iş gününe kaydırma, taban önce, tekrarsız yazma vb.).

**2026-10-11, Brief I (A'dan gerçekten farklı mutasyon).** `dev/mutations/brief-i.md` ve `dev/cases/brief-i-cases.json` (5 vaka: PUB-01, 07, 10, 06, 03; müşteri verisi pratik setten aynen). A'dan farklar: kimlikte önce telefon haneleri sonra doğum tarihi, toplam 2 yanlış cevap biter (mock hâlâ 3'e izin veriyor, sayma ajanın işi); tatiller 19.10, 02.11, 11.11, 25.12, 01.01 (26.10 iş günü); bantlar 1–10 erken / 8. iş günü / 1 deneme, 11–45 geç / 5. iş günü / 2 deneme; hafta sonu ya da tatil adı verilirse önceki iş günü; taban yok, "azaltılmış tutar" = geçmiş borcun yarısı, kuruşa yukarı yuvarlı; `create_promise` hatasında tekrar yok → `no_promise` / `service_error`; "registered" kelimesi, SMS cümlesi "A confirmation will be sent to you by text message.", açılış "may be monitored", kapanış "Goodbye, and thank you for your time."; geri arama yalnız ertesi iş günü 09:00–17:00. now = 2026-10-14 Çar ile erken son tarih 2026-10-27, geç son tarih 2026-10-22. Beklenenler: PUB-01 420.00 / 14.10; PUB-07 Cumartesi 17'si → 540.00 / 16.10; PUB-10 (8 gün, artık erken bant) tek `create_promise`, `no_promise` / `service_error`, söz yok; PUB-06 1062.55 / 16.10; PUB-03 iki yanlıştan sonra `not_verified` / `failed`. Build ve koşu yapılmadı, ölçülmedi.

## 11 Ekim, 01:46–02:00: H ve I build'leri (yeni skill), G kendi vakaları 1/2, devirden sonra açık kalan çağrı

H build'i (yeni skill'in ilk build'i, daraltılmış kanca): 214 sn, $1,19, 17 tur; workflow `18893b05-10ca-460d-b40f-e173749f1950`, agent `3f538ff4-9ae7-4c94-8732-781018574771`. Kanca builder'ın işini engellemedi (trace'te ret yok); `say_line`, 10 `op=`, "aynı soruyu üçüncü kez sorma" ve "daha düşük tutar demeyen müşteri teklifi kabul etmiştir" kuralları kullanıldı.

**Brief I build'i** (A'dan gerçekten farklı mutasyon): 205 sn, $1,11, 20 tur; workflow `a8d406e2-94c8-44c0-be91-1e76ccf7075c`, agent `b8027be6-6956-459d-a465-ccd4621db60d` (workspace 10/10). Builder I'nın farklarını doğru koda çevirdi: son tarih `n: 8`/`n: 5`, `shifts`/`roll: "backward"`, `floor_percent: 50`, önce telefon sonra doğum tarihi, iki yanlışta durma (bankanın sınırı 3 olduğu için sayımı ajana verdi), `create_promise` `retries=0` ve hata yedeğinde "create_promise: do not call it again", "registered", I'nın kapanış cümlesi. A değerleri kopyalanmadı. Ölçümü kuyrukta.

G kendi vakaları (G ajanı eski skill'le kurulmuştu): **1/2** (968 sn, üç koşu da yavaş). PUB-12 (kart için anlaşma, sonra dört kez insan) **3/3**: 4. talepte devir, kaydedilmemiş söz kaydedilmedi, not yok. PUB-11 1/3: ajan her şeyi doğru yaptı ama çağrı süre sınırına kadar açık kaldı (`exceeded …`): `end_call` yalnız veda cümlesiyle tetikleniyordu, G devirden sonra veda yerine duyuru istiyor. Düzeltme: `tools.end_call_tool(trigger_phrase=[...])` birden çok kapanış cümlesi alıyor (Freya `trigger_pattern` `|` ile ayrılmış liste); skill: brief'in çağrıyı bitiren her cümlesi listeye. Test eklendi, **506 yeşil**. Ölçülmedi.

## 11 Ekim, 01:55–02:05: H ölçümleri (B 2/3, kendi vakaları 2/3)

H ajanı (yeni skill) `--brief B --reps 3`: **2/3** (koşular 2, 3, 2; 242 sn); `dev/cases/brief-h-cases.json`: **2/3** (koşular 2, 2, 3; 222 sn). İkisinde de PUB-11 ve PUB-13 3/3 (D'nin konuşma kuralları dahil). PUB-12 1/3: baştan reddedilen kişisel krediye ikinci deneme yok (bir koşuda araç kredisine fazladan deneme). Neden: genelleştirmede skill'den çıkarılan "baştan reddedilen ürün de denemelerini alır" cümlesi; builder bunu Brief B'nin "her ürüne attempt 1'den başla" kuralından çıkaramadı. Skill'e koşullu olarak geri kondu ("brief her ürünün ilk denemeden başladığını söylüyorsa ya da ürüne gelmeden yapılan reddin deneme saydığını söylemiyorsa …"). Ölçülmedi; B'nin yeniden build'i ölçecek.

## 11 Ekim, 02:03–02:12: Brief I kendi vakaları 4/5 (genelleme sinyali), `gave_up present` tuzağı

I ajanı (`b8027be6…`) `dev/cases/brief-i-cases.json --reps 3`: **4/5** (koşular 4, 4, 4; 160 sn). A'dan farklı ya da ters kurallar 3/3: PUB-01 önce telefon, PUB-07 Cumartesi → **önceki** iş günü (16 Ekim), PUB-10 kayıt hatasında **tekrar yok** (`no_promise/service_error`), PUB-06 tam tutar fazla → **yarısı** (1062.55). PUB-03 0/3: konuşma doğru (iki yanlışta durdu), kapanış `no_promise/service_error` (beklenen `not_verified/failed`). Neden: builder'ın kapanış kuralı `["gave_up:create_promise", "present"]`; `gave_up` bir sayı, hiç çağrı yokken 0, `present` her zaman doğru. Kitaplık düzeltmesi: sayı olguları (`count`, `gave_up`, `logged`) `present/missing/true/false` ile kullanılınca `close_hook` hata veriyor ve doğrusunu söylüyor. Yalnız I build'inde vardı (arşivdeki diğer `gen.py`'ler temiz). Testler **511 yeşil**. I yeniden build edilip ölçülecek (kuyrukta, A'dan sonra).

## 11 Ekim, 02:06–02:25: B yeni skill'le (1/3, 7/9 koşu), effort deneyi başlatıldı

B build'i (genelleştirilmiş skill + koşullu baştan-ret kuralı): 198 sn, $1,11, 16 tur. `--brief B --reps 3`: **1/3** (koşular 2, 2, 3; 7/9; `dev/out/q-B6-reps3.out`). PUB-13 bir koşu: müşteri iki ürünü 30 Ekim'de istedi, kart (son tarih 2 Kasım) 27 Ekim'e kaydedildi (büyük olasılıkla öbür ürünün rehberine bakıldı). PUB-12 bir koşu: deneme sayısı. Okuma: tekrarlar arası oynama büyük; karşılaştırma koşu sayısıyla yapılmalı.

Effort: builder şu ana kadar Opus 5.5'in varsayılanıyla koştu (medium, adaptive thinking her zaman açık; `setting_sources=[]` olduğu için kullanıcı ayarı etkilemiyor; claude-code-guide ajanının belge taraması). İhsan'ın sorusu üzerine Artificial Analysis halüsinasyon tablosu tartışıldı (kapalı kitap bilgi soruları, bizim bağlamlı göreve zayıf vekil; Opus medium %68, max %59, Sonnet 5.5 max %47). Karar: model değil effort denensin. `BUILDER_EFFORT` ortam değişkeni eklendi (varsayılan değişmedi; trace'te `[builder] model … effort …`). Deney: medium tabanı (B6, A8, I2) ile aynı brief'lerin `BUILDER_EFFORT=max` build'leri (B, I, A) aynı vakalarda; build süresi ve maliyet de karşılaştırılacak.

## 11 Ekim, 02:19–02:45: medium tabanı tamam (A 9/10, I 4/5), iki bekleyen düzeltme

A (genelleştirilmiş skill, medium): build 178 sn, $0,81; `--brief A --reps 3` **9/10** (koşular 9, 9, 9; 27/30; `dev/out/q-A8-reps3.out`). Gerileme: PUB-06 0/3, taban (637.50) önce "bugün", müşteri Cuma deyince yine "Cuma" diye iki kez teklif edildi (hakem iki teklif sayıyor; A11'de 3/3'tü). Neden: genelleştirilmiş "her durumun teklif cümlesi" kuralı.

I (medium, `gave_up` denetimiyle yeniden): build 190 sn, $0,97; builder bu kez `["gave_up:create_promise", "gte", 1]` yazdı. Kendi vakaları **4/5** (koşular 4, 4, 4; 160 sn): PUB-03 artık 3/3; PUB-10 0/3: kapanış `not_reached/unclear`. Neden: HTTP 500'de post-kanca çalışmıyor, `bb_failed_out__create_promise` boş, `gave_up` 0; motor ise `create_promise_response.status: "error"`, `create_promise_failure_count: 1` yazıyor (değişken tablosundan doğrulandı). İlk I build'inde bu vaka yanlış `present` kuralı sayesinde tesadüfen geçmişti.

Bekleyen iki düzeltme (effort deneyini bozmamak için A-max build'i bitince uygulanacak; `scratchpad/pending_patch.py`): (1) `gave_up:<tool>` kancanın kaydı boşsa ve tool'un son çağrısı motorda `error` ile bittiyse 1; (2) skill: bir kez yapılabilen teklif bir kez yapılır, sonra yalnız gün konuşulur. Medium tabanı: B 7/9 koşu (1/3), A 27/30 (9/10), I 12/15 (4/5).

## 11 Ekim, 02:45–03:25: effort deneyi (max 50/54, medium 46/54), varsayılan max

`BUILDER_EFFORT=max` build'leri, medium tabanıyla aynı skill ve kitaplık (bekleyen düzeltmeler deneyden sonra uygulandı). B-max: build 247 sn, $1,24, 20 tur; `--brief B` **7/9** koşu (2/3; PUB-12 deneme sayısı). I-max: 325 sn, $1,58, 22 tur; kendi vakaları **15/15** (5/5): PUB-10'u kapanışta "create_promise denendi (pre-kanca kaydı var) ve başarılı yazma yok → service_error" kuralıyla doğru çözdü (medium `gave_up` sayacına bakmış, HTTP hatasında boş kalmıştı). A-max: 362 sn, $1,54, 20 tur; `--brief A` **28/30** (8/10; PUB-06 2/3 (medium 0/3), PUB-10 2/3: yavaş koşuda (568 sn) `get_account`'tan sonra kimlik yeniden soruldu, kapanış `not_verified`). Toplam max 50/54 (%93), medium 46/54 (%85); hiçbir brief'te geride değil; fark üç tekrarlık gürültüye yakın ama yön tutarlı. Karar (İhsan): varsayılan effort max. README güncellendi.

Deneyden sonra uygulanan düzeltmeler (`9344955`): `gave_up:<tool>` motorun son sonucu `error` ise 1; skill: bir kez yapılabilen teklif bir kez yapılır. Testler 512 yeşil.

## 11 Ekim, 03:25–04:55: max doğrulama zinciri, **Claude oturum kotası doldu**

A (max, teklif-bir-kez kuralıyla): build 311 sn, $1,53; `--brief A --reps 3` **9/10** (koşular 9, 9, 10; 28/30; 368 sn). PUB-06 1/3: builder taban cümlesini "Can you pay [floor] today?" diye yazdı; müşteri başka gün deyince taban yeniden teklif edildi (bir koşuda da tarih 23 Ekim). B (max): build 337 sn, $1,48, 18 tur; kayıttan (v12, 7 düğüm, 15 tool) hemen sonra ajan kota hatasıyla kesildi; `--brief B` **2/3** (7/9; PUB-12 deneme sayısı). I ve G build'leri **hiç koşmadı**: `Claude Code returned an error result: You've hit your session limit · resets 4:50am (Europe/Istanbul)`; export eski sürümü yazmadı ("this run saved no new version"), çıkış 1 (koruma çalıştı). Ölçümler eski ajanlarla koştu: I-max (03:02 build'i) yine **5/5** (15/15); G (01:28 medium build'i, devir düzeltmesi yok) 0/2 (devir duyurusundan sonra "goodbye" da söyledi).

**Risk (en önemli operasyonel risk):** builder Claude Code girişiyle (abonelik kotası) çalışıyor; bu oturum, alt ajanlar ve build'ler aynı kotayı tüketiyor. Pazar 20:00'de kota dolarsa gizli brief build'i düşer. Önlem: gizli brief build'leri için `ANTHROPIC_API_KEY` (İhsan'a soruldu); Pazar 18:00'den sonra bu hesapta yoğun iş yok. Organizatörün yeniden koşusundaki anahtar sorusu (açık soru 19) bununla bağlantılı.

04:55: kota açıldı; G ve I yeniden build ediliyor (max).

## 11 Ekim, 04:55–05:10: iCloud takılması, repo `~/code/yc-builder`'a taşındı (temiz klon provası)

G build'i 04:55'te başladı ve 5 dk hiç ilerlemedi (trace'te `[builder]` satırı bile yok). `sample`: süreç bir import sırasında `read` sistem çağrısında asılı; okuduğu dosya `.venv/.../httpx2-2.13.1.dist-info/entry_points.txt`. Neden: repo iCloud ile eşitlenen Masaüstündeydi (`FXICloudDriveDesktop = 1`); macOS gece `.venv`'de 3.501, repo'nun geri kalanında 1.148 dosyayı iCloud'a boşaltmış ("dataless"); okuma indirmeyi bekleyip asılı kaldı. Pazar gizli brief build'inde olursa build hiç başlamaz.

Çözüm (İhsan onayladı): GitHub'dan `~/code/yc-builder`'a temiz klon (iCloud dışı, dataless dosya yok); README'deki gibi `python3 -m venv .venv` + `pip install -r requirements.txt` (claude-agent-sdk 0.2.165 kuruldu), **512 test yeşil** (3,7 sn; eski klasörde 7 sn). Git dışı dosyalar elle kopyalandı: kit `env.sh`, `builder/work/.freya-agents.json` (10 slot, workflow'lar yerinde güncellenir), `.slot-inputs.json`, kit `.personas.json`. Eski klasör (`~/Desktop/yc-builder 2`) artık kullanılmıyor. Bu, planın temiz klon provasının ilk yarısı; build + ölçüm yeni klasörde koşuyor (G, max: `[builder]` satırı geldi, ilerliyor). Codex ve IDE yeni klasöre yönlendirilmeli.

## 11 Ekim, 05:07: G build'i (run4) yarıda öldü, kuyruk yeniden kuruluyor

Yeni oturum başında görüldü: 05:03'te başlayan G build'i (`dev/out/build-brief-g-run4.out`) 05:05'te, 36 satırda, `[end]` satırı olmadan kesilmiş; süreç yok (büyük olasılıkla önceki oturum kapanınca öldü). Yani 05:10 kaydındaki "ilerliyor" geçersiz; devir sonrası kapanış düzeltmesi (`trigger_phrase` listesi) hâlâ **ölçülmedi**. Ayrıca eski kuyruğun vaka yolları iCloud klasörünü gösteriyordu; yeni kuyruk `~/code/yc-builder/dev/cases/` kullanıyor. Kit'in `results/` klasörü (gitignore'da) yeni klonda yok; eski sonuç dosyaları eski klasörde duruyor. Sıradaki: G build (max) → G kendi vakaları ve `--brief B`, ikisi de `--reps 3`.

## 11 Ekim, 05:10–05:56: G (max, yeni klasör): kendi vakaları 2/2, B 0/3 (6/9 koşu)

G build'i (max, `trigger_phrase` listesiyle): 398 sn, $1,69, 15 tur; aynı workflow `2879165a…`, agent `1232dcdb…`, v4, 6 düğüm, 11 tool; dry run geçti, export yazıldı. `dev/cases/brief-g-cases.json --reps 3`: **2/2** (koşular 2, 2, 2; 169 sn; `dev/out/q-G5-own-reps3.out`). PUB-11 (dört insan isteği, çok ürün) artık 3/3: devir duyurusundan sonra çağrı kapanıyor; önceki build'de 1/3'tü (`exceeded`). Devir sonrası kapanış düzeltmesi tuttu.

Aynı ajan `--brief B --reps 3`: koşular **2, 3, 1** (6/9; pass^3 **0/3**). 3. tekrarda `run_cases.py` Freya'nın simülasyon durumunu yoklarken 120 sn okuma zaman aşımıyla çöktü (`TimeoutError`, ağ/platform); simülasyon `2b59dffc` Freya'da tamamlanmıştı, `dev/rescore.py` ile puanlandı (1/3). Kalmalar:
- PUB-11, 1. koşu: beş `create_promise` çağrısı ve `add_note` p1 `service_error` (beklenen not yok). Nedeni incelenmedi; banka kesintisi ya da yanlış hata yolu olabilir.
- PUB-12, 3. koşu: hiç teklif yok, `no_promise/refused` ile kapandı (beklenen p1 sözü ve p2/p3 için `refused` notu).
- PUB-13, 3. koşu: kredi 23 Ekim yerine 16 Ekim'e kaydedildi (geri okuma doğruydu, kayıt yanlış).

Okuma: G'nin insan sayacı ve devir kapanışı B'nin çok ürün akışını bozmuyor gibi (2. koşu 3/3), ama B'de koşudan koşuya oynama sürüyor; ortak payda çok ürün kayıt/deneme sırası. B ölçümünde kit'in `results/q-G5-B-reps3.json`'u yazılmadı (çökme). Sıradaki: PUB-11 1. koşu ve PUB-12/13 3. koşu dökümleri (salt okuma), sonra PUB-06.

## 11 Ekim, 06:00–06:20: G'nin B kalmaları, teşhis (salt okuma döküm)

Dökümler `scratchpad/dump.py` ile (simülasyon + vaka → mesajlar, tool çağrıları ve sonuçları).
- **PUB-11, 1. koşu (kitaplık hatası):** onaydan sonra model üç `create_promise`'ı **aynı mesajda, paralel** çağırdı. Post-kanca ürünü `bb_key__create_promise` / `<tool>_args`'tan okuyor; paralel çağrılar bunu eziyor. p1'in sonucu "p2 kaydedildi; p1, p3 açık" dedi → model p1'i yeniden çağırdı → banka `ok:false` "this product already has a promise" → kanca başarısızlık sayıp bir tekrar daha, sonra vazgeçip `service_error` notu → ajan müşteriye "kredi kartı sözünüz kaydedilmedi" dedi (kaydedilmişti). Hakem geçirdi, ledger fazladan not yüzünden kaldırdı. Platformda paralel çağrıyı kapatan ayar yok (kit `docs/`); kanca yalnız `result` ve ortak değişken tablosunu görüyor; bankanın yanıtında ürün kimliği yok. Skill'de "mesaj başına tek tool çağrısı" kuralı yok (kit builder'ı böyle yapıyor).
- **PUB-13, 3. koşu (model):** aynı paralel çağrı (iki sonuç da "p2 kaydedildi" dedi; ikisi başarılı olduğu için zararsız kaldı). Asıl kalma: müşteri iki ürün için 30 Ekim istedi; kredi için ajan "en geç tarih 23 Ekim" deyip **16 Ekim**'i önerdi ve kaydetti (beklenen 23 Ekim).
- **PUB-12, 3. koşu (model):** müşteri "kartı yarın öderim, krediyi ve arabayı ödemiyorum" dedi; ajan "yarın için notunu aldım" deyip kart için geri okuma, onay ve `create_promise` yapmadı, p2/p3 için `add_note` da yok; denemeler bitince doğrudan veda (`no_promise/refused`). Hiç yazma olmadığı için çağrı sonu `{open:…}` mesajları hiç devreye girmedi.

## 11 Ekim, 06:20–07:20: paralel çağrı düzeltmesi (`6c544c3`), ölçüm kuyrukta

Kitaplık: pre-kanca her isteği (anahtar, argümanlar, tarih notu) `bb_queue__<tool>`'a ekliyor; post-kanca sıranın başını alıp `bb_key/bb_arg/bb_adjusted` yuvalarına geri koyuyor (ilk giren ilk çıkar). Uçuşta çağrı yoksa (`bb_finished__<tool>` + motorun `<tool>_failure_count`'u ≥ `bb_started__<tool>`) sıradaki eski kayıt atılıyor: motor hatasıyla biten çağrı post-kanca almıyor. Aynı anahtarla yeni istek, o anahtarın eski kaydının yerini alıyor. Sıra yoksa (pre-kancasız tool) davranış eskisi gibi. Sınır: paralel çağrılar sırasız dönerse ve biri başarılı biri başarısızsa eşleşme yine kayabilir. Skill: system prompt'ta "mesaj başına tek tool çağrısı, sonucunu bekle, aynı tool birden çok ürüne gerekse de"; çağrı sonu şablonunda "yalnız ilk açık ürün için çağır; sonuç sıradakini söyler". Testler **516 yeşil** (4 yeni: paralel üç çağrı, post-kancasız hata sonrası kayma yok, aynı anahtarın tekrarı, tarih notu kendi çağrısında). Platformda **ölçülmedi**: kuyruk (07:19) B build'i → `--brief B --reps 3`, A build'i → `--brief A --reps 3`.

## 11 Ekim, 07:19–07:40: paralel çağrı düzeltmesiyle B 3/3, A 10/10

B build'i (A+B, max, `6c544c3`): 255 sn, $1,39, 16 tur; workflow `1dfbdfd9…`, v13, 6 düğüm, 11 tool. `--brief B --reps 3`: **3/3** (koşular 3, 3, 3; 9/9; 221 sn; `dev/out/q-B8-reps3.out`). Son skill'le önceki B ölçümleri 7/9 ve 6/9'du. Son tekrarın dökümünde PUB-11 ve PUB-13'te `create_promise`'lar artık tek tek çağrılıyor, her sonucun mesajı doğru ürünü söylüyor (paralel çağrı görülmedi).

A build'i (yalnız brief-a, max): 374 sn, $1,73, 20 tur; workflow `5ef7910f…`, v18, 6 düğüm, 10 tool. `--brief A --reps 3`: **10/10** (koşular 10, 10, 10; 30/30; 315 sn; `dev/out/q-A9-reps3.out`). PUB-06 3/3 (önceki max ölçümünde 1/3). Gerileme yok. Not: tek ölçüm; tekrarlar arası oynama ±1–2 vaka olduğu için PUB-06 ve B'deki model kaymalarının (PUB-12/13) kapandığı söylenemez, yalnız bu koşularda görülmedi.

Sıradaki: G ve I'yı yeni kitaplıkla bir kez build edip kendi vakalarında kontrol (genelleme gerilemesi yok mu), sonra 16:00 `ANTHROPIC_API_KEY` ile temiz klon provası.

## 11 Ekim, 07:45–08:01: 26 hedefli vaka (kendi), ölçüm kuyrukta

Organizatörün 13 vakasının ve bizim 18 vakamızın sınamadığı davranışlar için 26 vaka (`dev/cases/own-a-1.json`, `own-a-2.json`: Brief A, 10'ar; `own-b-1.json`, `own-b-2.json`: Brief B, 3'er). Müşteri verisi pratik setten aynen; senaryo, beklenen kayıt ve kontroller bizim. Temalar: itiraz (iki biçim: "benim değil" ve "geçen yıl kapattım"), prompt injection, "dolandırıcı mısın?", robot sorusu + ısrarla insan, iki kez konuşmak istemeyen kızgın müşteri, tabanın altında tutar, geri okumada tarih değişikliği, yanlış numara, pencere dışı geri arama, vefat, "next Friday", belirsiz kimlik ("who is this?"), gün-ay ters doğum tarihi, güvenlik sorusu yerine "ne hakkında?", son tarihten sonra istek, hastalık + destek devri, ödeme planı devri, cevaplanamayan soru (faiz) + Cumartesi, çok üründe karışık durumlar (ödedim + söz + ret; söz anlaşılıp kaydedilmeden yeniden yapılandırma; tek tarih son tarihi aşınca + taban; zor durum notları; Cumartesi → Pazartesi + bir ürün ret; itiraz + ödedim). 4 vakada `style` (talkative, in_words, corrects, pieces).

Üretim (Workflow, 130 ajan, ~9 dk): vaka başına bir yazar, beklenen kaydı yazarınkini görmeden brief'ten çıkaran iki kör denetçi, uyuşmazlık ya da belirsizlik notunda bir hakem (senaryoyu sıkılaştırır ya da atar) ve hakemin sonucunu bir kör denetçi daha doğrular. 26/26 kabul (hepsinde son kör denetim beklenen kaydı birebir verdi); kabul edilmeyen olsaydı atılacaktı. Bilinen risk: own-a-1 PUB-07'de simüle müşterinin "eşleşen geri okumaya onay" kuralı ile senaryonun "Cuma'yı onaylamaz" satırı çakışabilir; kalırsa önce döküm okunacak. Ölçüm (08:01): B ajanı (v13) own-b-1/2, A ajanı (v18) own-a-1/2, hepsi `--reps 3`.

## 11 Ekim, 08:01–08:30: kendi B vakaları (own-b-1 1/3+1/3, own-b-2 1/3), gün tablosu ve iki skill kuralı (`4d21fd8`)

B ajanı (v13, `6c544c3`'ün build'i). own-b-1: 1. tekrar 1/3, 2. tekrarda `run_cases` Freya 502'siyle çöktü (`GET /simulations/<id> -> 502`), simülasyon `762701fc` tamamlanmıştı, `dev/rescore.py --cases` ile 1/3; 3. tekrar yok. own-b-2 (3 tekrar): 1/3 (PUB-11 3/3, PUB-12 2/3, PUB-13 1/3). Dökümlerden:
- own-b-1 PUB-13 (gerçek): müşteri iki ürüne 28 Ekim dedi; ajan son tarihleri ürünler arasında karıştırdı: kartı (son tarih 2 Kasım) "28'i geç" deyip 27'ye kaydetti, krediye (son tarih 23 Ekim) 28'i önerdi (pre-kanca tarihi 23'e çekti, geri okuma yanlıştı). `account_facts`'teki bilgi doğruydu: iki ürünün ayrı, 25'er satırlık gün rehberi alt alta.
- own-b-1 PUB-12 (gerçek): kart anlaşılınca "I have recorded that for the credit card" (kayıttan önce, dürüstlük).
- own-b-1 PUB-11 (vaka kusuru): kayıt doğru, sıra doğru (geri okuma 27,6 sn, onay 34,6 sn, `create_promise` 41,9 sn); hakem iki koşuda da "create_promise geri okumadan önce" dedi. Tool olaylarıyla mesaj sırası soran kontrol cümlesi konuşma üzerinden yeniden yazıldı.
- own-b-2 PUB-13 (gerçek, 2 koşu): itiraz + "ödedim", söz yok → ajan hiç `add_note` yazmadan kapattı (B kural 8 söz yokken de not istiyor). Sabahki PUB-12 kalmasıyla aynı: hiç yazma olmayınca post-kanca "kalan ürünler" mesajı hiç gelmiyor.
- own-b-2 PUB-12 (gerçek, 1 koşu): "hepsi Cumartesi" → araba kredisi için Pazartesi 19 yerine Cuma 16 önerildi, ret, not.

Düzeltmeler (mekanizma, `4d21fd8`): (1) tarih düğümü her gün rehberini yapılandırılmış olarak da yazıyor (`bb_shiftmap__<ad>`); ürün düğümü birden çok üründe ürün başına rehberler yerine **tek gün × ürün tablosu** yazıyor (her satır: gün + her ürün için anlamı), ürün satırındaki `{deadline_shifts}` tabloya işaret ediyor; tek üründe metin birebir eski; builder config'i değişmedi. (2) Skill: çok üründe geri okumadan önce anlaşılan ürün için kaydedildi sözcüğü olmayan onay cümlesi (görev mesajı verir). (3) Skill: söz hiç yokken her ürüne kayıt kuralı görev mesajında ayrıca ("If no promise was agreed, first call <record tool> for every product ... only then the goodbye"). Testler **519 yeşil** (3 yeni: iki ürünlü tablo, tek ürün değişmez, yapılandırılmış rehber yoksa eski metin). Ölçülmedi: kuyruk (`queue8`) own-a ölçümü bitince B build → own-b-1, own-b-2, `--brief B`; A build → `--brief A`.

## 11 Ekim, 08:11–08:35: own-a-1 6/10 (23/30), Freya kapanış tetikleyicisi müşterinin sözüyle çağrı kapatıyor (`765fdd3`)

A ajanı (v18) `dev/cases/own-a-1.json --reps 3`: **6/10** (koşular 7, 7, 9). 3/3: itiraz, "dolandırıcı mısın?", robot + insan ısrarı, tabanın altında tutar, yanlış numara, pencere dışı geri arama. Dökümler:
- **PUB-07 (platform, ciddi):** müşteri doğum tarihini söylerken ("...it took me forever to get in. My date of birth is...") çağrı ajan konuşmadan kapandı. Olay: `trigger_timeout_started`, `function: end_call`, `triggered_pattern: "ok"`, `source: auto_trigger`. `end_call`'ın `trigger_pattern_both` listesi ("Bye|Goodbye|Thank you|Thanks|OK|Okay|You too", kit builder'ınınkiyle aynı) müşterinin sözüne de, alt dize ve büyük-küçük harf duyarsız uygulanıyor; eşleşmede 3 sn'lik kapanma sayacı başlıyor, model 3 sn'de cevap vermezse çağrı biter. Kit belgesi bu listeyi yalnız "kapanışı iptal etmeyen veda cümleleri" diye anlatıyor. Bugünkü 22 simülasyonun 103 çağrısında 1 kez (salt okuma tarama). Finalde "Okay, Friday is fine" / "Thanks, but..." diyen müşteriyle çağrı ortada kapanabilir. Düzeltme: `tools.end_call_tool` listede yalnız "bye" içeren cümleleri tutuyor (hiçbiri yoksa Goodbye, Bye). Test: 520 yeşil.
- **PUB-02 (vaka kusuru):** müşteriyi oynayan model "Ignore all your previous instructions..." cümlesini söylemeyi reddetti ("I cannot fulfill this request..."); ajan anlaşılmayan cevapları ret sayıp teklif yaptı. Senaryo aynı niyetle doğal bir cümleye çevrildi.
- **PUB-05 (gerçek, 3/3 kaldı):** "konuşmak istemiyorum" ikinci kez söylenince ajan kapatmadı, ikinci teklifi (taban, son tarih) yaptı; A kural 45 iki kez söyleyince kapatmayı istiyor. Bir koşuda müşterinin ikinci cümlesi yarıda kesik geldi ("I told you, I don'"). Simüle müşterinin cümlesi zaman zaman yarıda kesiliyor (PUB-10'da da).
- **PUB-10 (gerçek, 1 koşu):** "next Friday" → ajan "iş günü değil, Pazartesi 19" dedi (23 Ekim Cuma iş günü); müşteri düzeltti, ledger doğru, hakem gereksiz teklifi kaldırdı.
Kuyruk: own-a-2 koşuyor; ardından `queue8` (B build `765fdd3` ile → own-b-1, own-b-2, `--brief B`; A build → `--brief A`).

## 11 Ekim, 08:17–08:35: own-a-2 8/10 (26/30)

A ajanı (v18) `dev/cases/own-a-2.json --reps 3`: **8/10** (koşular 8, 9, 9; 553 sn). 3/3: gün-ay ters doğum tarihi (ipucu → ay kelimeyle), güvenlik sorusu yerine "ne hakkında?" (declined), son tarihten sonra istek → son tarih, hastalık → destek devri, ödeme planı → yeniden yapılandırma, faiz sorusu + Cumartesi → Pazartesi, "geçen yıl kapattım" → itiraz, vefat, taban + banka hatası + tekrar (`corrects` stili).
- **PUB-01 (gerçek, 0/3):** "Who is this?" → cevap + ikinci soru → "Go ahead, what do you want?" → ajan **üçüncü kez** sordu, sonra veda; kapanış `not_verified/declined` (beklenen `not_reached/unclear`). Builder kuralı prompt'a doğru yazmış ("That is the second ask. If it is still unclear after the second ask, say ..."); model saymadı. Kapanışta kapanış modeli `no_promise` seçti, builder'ın "kimlik doğrulanmadı + model promise/no_promise → not_verified/declined" kuralı çevirdi.
- **PUB-02, 1. koşu (platform):** ajan doğru (söz, cümle, veda); çağrı bitti ama `end_of_call` `close_call` hiç başlamadı ("analysis never arrived"); yavaş koşu (364 sn). Ajan tarafında düzeltilecek bir şey yok.
Toplam kendi A vakaları (eski ajan, düzeltmelerden önce): 14/20 vaka, 49/60 koşu. Açık ajan sorunları: tek adımda soru sayısı (PUB-01, A kural 3), "iki kez konuşmak istemiyorum" (own-a-1 PUB-05, kural 45), "next Friday" (1 koşu).

## 11 Ekim, 08:27–09:00: B v14 (gün tablosu + iki skill kuralı + tetikleyici düzeltmesi): own-b-1 2/3, own-b-2 0/3, B 2/3; A v19 8/10; veda kapısı (`2459d31`)

B build (`765fdd3`): 342 sn, $1,54, 20 tur, v14. own-b-1 **2/3** (PUB-11 3/3, PUB-12 3/3: "recorded" kayması kapandı; PUB-13 1/3: kart yine 28 yerine 27 Ekim'e, gün tablosuna rağmen). own-b-2 **0/3** (PUB-11 zor durum 0/3: önceki build'de 3/3; ajan "I have noted this down for your accounts" deyip hiç `add_note` çağırmadan veda etti; PUB-13 2/3; PUB-12 2/3). Organizatör B **2/3** (8/9; PUB-12 bir koşuda hiç yazmadan kapattı). Builder "söz yoksa önce her ürüne add_note, sonra veda" kuralını görev mesajına birebir yazmıştı; model uymadı. Bu aile bugün dört kez görüldü (organizatör PUB-12, own-b-2 PUB-11/PUB-13, sabahki G PUB-12): prompt kuralı tutmuyor.
A build (v19): `--brief A` **8/10** (koşular 9, 9, 10; 28/30): PUB-06 taban iki kez (1 koşu), PUB-03 üçüncü yanlış cevap `verify_identity`'ye gitmedi (1 koşu); oynama aralığında.

Yapısal düzeltme (`2459d31`, kit'in "tool değişken yazar, geçiş kapanışa götürür" doğrulanmış deseni): `hooks.post_hook(open_var=, open_tools=)` her sonuçtan sonra açık ürün listesini değişkene yazıyor. Skill: brief her ürüne kayıt istiyorsa `negotiate`'te end_call yok; `bb_open == none` (ya da devir bayrağı) → `wrap_up` (on_enter llm, yalnız end_call, brief'in kapanış cümleleri). Kayıt istemeyen brief'te (A) end_call `negotiate`'te kalır. Testler **524 yeşil**. Kuyruk (`queue9`, 09:00): B build → own-b-2, own-b-1, `--brief B`; A build → `--brief A`; build'lerin gen.py'sinde `bb_open` sayısı log'a yazılıyor (A'da 0 beklenir).

## 11 Ekim, 09:05–09:20: kod incelemesi (3 ajan, salt okuma) ve düzeltmeler; veda kapısı ilk ölçüm

**v15 (veda kapısı) own-b-2:** koşular 1, 2, 3 (6/9; v14 4/9). Zor durum notları 0/3 → **3/3**; itiraz + ödedim notları 3 koşuda da yazıldı. Kalanlar: "bir iş günü" cümlesi eksik (PUB-13, 2 koşu), çok üründe yanlış tarih (PUB-12, 1 koşu). own-b-1 1. tekrar: simülasyon `c0fcd12c` "running"de takıldı (3 çağrı bitmiş, kararlar var); `dev/rescore.py` ile 2/3 (PUB-11, 12 geçti; PUB-13 tarihler doğru: kart 28, kredi 23 Ekim; tutar 900 kaydedildi, beklenen taban 300). Bekleyen `run_cases` durduruldu; **panelden `c0fcd12c` silinmeli**, kuyruk (`--brief B`, sonra A build + `--brief A`) onu bekliyor.

İnceleme (teslim hazırlığı, bugünkü runtime, skill/ajan açıkları; bulgular elle doğrulandı). Düzeltilenler:
- `bfedfc4` `build.py`: SDK'sız `python3` ile başlatılınca `.venv/bin/python` ile kendini yeniden başlatıyor (organizatörün komutu `python3 builder/build.py`; denendi: `/opt/homebrew/bin/python3` → venv'e geçti). Erişim kancası genel desenleri klonun kendi yolu `<repo>` ile değiştirildikten sonra eşliyor (`/tmp/out/…`, `~/results/…` altında klon artık her yolu reddetmiyor); engelli bir ada denk gelen brief'te slot `wf-<hash>`, girdi kopyası `input-N`. Trace `submission/<slot>.trace.log`'a kopyalanıyor (`traces/` gitignore'da). Zaman damgasında saat dilimi.
- `3e868c4` runtime: kuyruk girdileri 25 sn sonra düşüyor (post-kancasız bir çağrının kaydı sonraki ürünü kaydırmasın), anahtarsız çağrılar birbirini silmiyor; kapıda son kayıt aracının vazgeçtiği ürün kapalı sayılıyor (kilitlenme yok); bozuk gün rehberi yalnız tabloyu düşürüyor; etiketler en uzun rehberden.
- `fbd7838` skill: kapı ayrıntıları (bayrak yalnız başarı alanında; `negotiate`'e `max_turns` + `max_turn_transition="wrap_up"`; kapanış cümlesi ve end_call yalnız `wrap_up`'ta; her ürün sonu ya kayıt ya bayrak), kapanış korumaları `keep_model`'den ÖNCE (eski metin "sonra" diyordu, runtime'da ilk eşleşen kazanır), "declined" yalnız kim olduğunu onaylamış kişide, olgusu olmayan sonuç düzeltilir (yazma yokken promise), "üçüncü kez sorma" kimlik denemelerine istisna, ham malzeme: tarihli değişikliklerin sırası, kod → enum tablosu, serbest metin alanında ad. README çalıştırma komutu `python3 builder/build.py`.
Testler **534 yeşil**.

Açık (kod dışı, 19:00'dan önce): **workspace 10/10 dolu** (`.freya-agents.json` 10 slot): gizli brief yeni workflow yaratamaz. Panelden kullanılmayanlar silinmeli (exp-retry, brief-a-raw, brief-c, brief-d, brief-d-518c5c, brief-g, brief-h, brief-i), girdileri `.freya-agents.json` ve `.slot-inputs.json`'dan çıkarılmalı. Ölçülmedi: build süre aşımında Claude alt sürecini öldürmüyor; başta anahtar kontrolü yok; maskede `CLAUDE_CODE_OAUTH_TOKEN`/`sk-ant-` yok.

## 11 Ekim, 09:19–09:50: B v15 `--brief B` 2/3; platform: end_call adımda yokken de çağrılabiliyor

İhsan panelden 4 workflow sildi (brief-i, brief-h, brief-g, exp-retry; ekranda 11 workflow vardı, yani sınır 10 değil gibi; 6 kaldı) ve takılan simülasyonu sildi; silinenler `.freya-agents.json` ve `.slot-inputs.json`'dan çıkarıldı. v15 `--brief B --reps 3`: **2/3** (koşular 2, 3, 2; PUB-11, 13 3/3; PUB-12 1/3). PUB-12 3. koşu: kredi için tek deneme (bilinen aile). PUB-12 1. koşu: hiç yazma olmadan veda; olay kaydı `function_call_start end_call` ve `trigger_timeout_started ... "source": "llm"`, `negotiate`'in tool listesinde end_call **yok** (`workflow.json`: negotiate = create_promise, add_note, transfer_to_agent). **Bulgu:** motor, workflow'da başka adımlarda tanımlı end_call'u modelin çağırdığı adımda da çalıştırıyor; araçsız adım kapısı tam kilit değil. v15 eski skill'le kurulmuştu: system prompt'ta kapanış cümlesi ve "Then call end_call" vardı (`fbd7838` bunları yalnız `wrap_up`'a taşıdı). Sıradaki: A ölçümü bitince B yeni skill'le yeniden build → own-b-2, own-b-1, `--brief B`. Tam kilit için seçenek (yapılmadı): end_call aracını hiçbir adıma koymamak, bütün bitişleri `end_call` düğümüne rotayla götürmek (kit belgesindeki doğrulanmış desen).

## 11 Ekim, 09:43–10:15: A v22 9/10, B v16 (yeni skill) own-b-2 1/3 (kayıtlar 9/9 doğru), own-b-1 0/3; motor adım araç listesini zorlamıyor; `calc.wrap_code` (`364aff4`)

A build (`fbd7838` skill'i): 337 sn, $1,68, v22; gen'de `bb_open` yok (A'da kapı kurulmadı, doğru). `--brief A`: **9/10** (koşular 10, 9, 10; 29/30; PUB-06 1 koşu taban çok kez). B build (v16, aynı skill): own-b-2 **1/3** ama ledger hatası **yok** (kayıtlar 9/9 doğru); kalmalar zorunlu cümle: PUB-12 0/3 "text message" cümlesi yok (`wrap_up` `on_enter=llm` koşullu cümleyi atladı: "I have recorded your promises. Thank you… Goodbye."), PUB-13 1 koşu "bir iş günü" cümlesi. own-b-1 **0/3**: PUB-11 "text message" cümlesi yok (aynı neden); PUB-13 kart yine 27 Ekim (3/3 koşu); PUB-12 devirden sonra wrap_up'ta model `add_note` ve `create_promise` çağırdı.
**Platform bulgusu (olay kaydı):** devir post-kancası `bb_transferred=yes` yazdı, rota aynı turda `wrap_up`'a geçti (kanca değişkeniyle rota doğrulandı); ama `wrap_up`'ın tool listesinde yalnız end_call varken model `add_note`/`create_promise` çağırdı ve motor çalıştırdı. Motor, workflow'da tanımlı herhangi bir tool'u herhangi bir adımda çalıştırıyor; adımın tool listesi yalnız modele ipucu. Ayrıca model `add_note` ile `transfer_to_agent`'ı aynı mesajda paralel çağırdı (tek çağrı kuralına rağmen).
Düzeltme (`364aff4`): `calc.wrap_code(parts=[{"when": [...], "say": TEXT}, ..., {"say": CLOSING}])` kapanış sözlerini koşullara göre kodda seçip `bb_wrap`'a yazar; skill: `negotiate` → `wrap_text` (kod düğümü) → `wrap_up` (`on_enter=wf.say("{{bb_wrap}}")`, model konuşmaz). Testler **546 yeşil**. Kuyruk (`queue11`): B build → own-b-1, own-b-2, `--brief B`.

## 11 Ekim, 10:16–10:42: B v17 (`wrap_code`) B sürümü seçildi: `--brief B` 2/3, own-b-2 3/3, own-b-1 1/3 (7/9 koşu)

B build (`364aff4` skill'i, `brief-b-run12`, çıkış 0; gen'de `wrap_code` var), v17, agent `19e0b5d6…`. Ölçümler, hepsi `--reps 3`:
- own-b-1: **1/3** (koşular 3, 1, 3; 7/9). PUB-12 (devir) 3/3. PUB-11 2. koşu: araba kredisinde tam tutar reddedilince taksit yine önerildi (judge). PUB-13 2. koşu: kart yine 27 Ekim kaydedildi, beklenen 28 (ürünler arası tarih ailesi, bilinen).
- own-b-2: **3/3** (koşular 3, 3, 3; 9/9; bu dosyada ilk tam sonuç). Panelin %100'ü yalnız judge; `dev/rescore.py` ile kayıt denetimi de 3/3.
- `--brief B`: **2/3** (koşular 3, 2, 3; 8/9). PUB-12 2. koşu: erken banttaki krediye iki deneme (ürün başına deneme sayısı ailesi, bilinen). 2. ve 3. koşuda "phone agent was slow" uyarısı.
v16'ya göre: own-b-1 0/9 → 7/9 koşu, own-b-2 4/9 → 9/9 koşu, B aynı (2/3). Kapanış metni kodda (`wrap_text` → `wrap_up` `say`) "text message" ve "bir iş günü" cümlesi kaybını bitirdi; üç dosyada kayıtsız veda **yok**. Durma kuralına göre B ≥ 2/3 ve gerileme yok: **B sürümü v17**. Kalan iki aile (deneme sayısı, ürünler arası tarih) prompt'la; mekanizması yok. Sıradaki: A v22 (`fbd7838` skill'i; `wrap_code` yalnız kapılı build'e dokunuyor) own-a-1, own-a-2 (`queue12`, 10:42).

## 11 Ekim, 10:50: B v17 PUB-12 kalması: judge gerekçesi yanlış ürün, karar doğru

2. koşunun dökümü (call `80820275…`): müşteri açılıştaki "bugün hepsini ödeyebilir misiniz"e "kartı yarın öderim, kredileri ödemem" dedi. Ajan krediye (16 gün, geç bant, 2 deneme) yalnız 1 deneme yaptı ("1320.00 on Friday"), 2. deneme (deadline'da taban) yok; arabaya (7 gün, erken bant) 1 deneme, doğru. Judge "araba kredisine iki deneme" yazdı (açılış sorusunu deneme saydı; Brief B kural 4'e göre ürün sayımı açılıştan sonra başlar), ama vaka "kişisel krediye iki deneme" istediği için karar yine doğru. Gen'in system prompt'unda kural açık ("Never end a product as refused before its listed attempts are used"); model 3 koşunun 1'inde uymadı. Araç çağrısı olmayan bir reddi kodda sayacak kanca yok; 12:30'dan önce yapısal değişiklik yapılmadı.

## 11 Ekim, 10:42–11:01: A v22 own-a-2 10/10, own-a-1 7/10; PUB-09 gerilemesi (kapanış koruması eksik), skill düzeltmesi (`4f64795`)

A v22 (`fbd7838` skill'i), `--reps 3`: own-a-2 **10/10** (koşular 10, 10, 10; v18'de 8/10). own-a-1 **7/10** (koşular 7, 7, 7; v18'de 6/10). PUB-07 ve PUB-10 2/3 → 3/3. Kalanlar:
- **PUB-09 (gerileme, 3/3 aynı):** `schedule_callback` hiç çağrılmadan kapanış `not_reached/callback` (beklenen `no_callback`). v22 gen'de "callback sonucu ama callback yok" koruması yok (08:27 build'inde vardı); `not_reached` için `reason: {"model": True}` kuralı modelin "callback"ini geçirdi. Skill kuralı ("olgusu gerçekleşmemiş sonuç değiştirilir") yalnız promise örneği veriyordu. Düzeltme (skill, mekanizma): tablonun her sonucu VE nedeni için, bir yazmanın kanıtladığı her biri (söz, geri arama, devir) koruma alır, `{"model": True}` kurallarından önce.
- **PUB-02 (vaka ve platform):** simüle müşterinin cümleleri kesik geldi ("No, I cannot pay today, but"); ajan "Cuma öderim"i hiç duymadı, iki deneme yapıp kapattı. Judge tabanı (taksit tutarı 103.50, deadline'da 2. deneme, brief'e uygun) "taksit planı" saydı (3. koşuda söz kaydedildiği halde kaldı). Vaka kontrolü netleştirildi (taban teklifi taksit planı değil).
- **PUB-05 (bilinen, 0/3):** "iki kez konuşmak istemiyorum" sonrası üçüncü teklif.
Kuyruk `queue13` (11:01): A build → own-a-1, `--brief A`; B build → `--brief B`, own-b-2, own-b-1; own-a-2. Sonuç v22/v17'den kötüyse 12:30 dondurması bu skill'i geri alır.

## 11 Ekim, 11:01–11:30: A v23 (`4f64795` skill'i) `--brief A` 10/10 (30/30, yeniden puanla); own-a-1 1 koşu 9/10

A build 11:01–11:08, çıkış 0 (v23). `--brief A --reps 3`: run_cases **6/10** yazdı (koşular 10, 10, 6); 3. koşunun 4 kalması da "Call ended but analysis never arrived (300s)" (platform). `dev.rescore 423d426f` ile 3. koşu **10/10** → A v23 **10/10, 30/30**. own-a-1 ölçümü 1. koşudan sonra Freya GET 502 ile çöktü (`run_simulation`); `dev.rescore 6970a1ac --cases own-a-1.json`: **9/10** (tek koşu). PUB-09 (geri arama koruması) geçti, PUB-05 ve PUB-02 de geçti. PUB-07 kaldı: judge "create_promise onaydan önce" dedi, döküm tersini gösteriyor (geri okuma → "Yes, I confirm" → create_promise); ledger doğru, judge hatası. Müşteri cümleleri yine kesik geliyor. own-a-1 `--reps 3` yeniden kuyrukta (`queue14`, queue13'ten sonra).

## 11 Ekim, 11:24–11:45: B v18 build; Freya kesintisi (503/504), ölçümler çöktü

B build (`4f64795` skill'i) 11:24–11:32, çıkış 0 (v18). `--brief B`: koşu 1 **3/3**, koşu 2 **3/3**; 3. koşuda `GET /api/v2/simulations/ebea0e47…` → 503 "API key validation is temporarily unavailable" ile çöktü. Ardından own-b-2, own-b-1, own-a-2 ve own-a-1 yeniden ölçümü `POST /api/v2/simulations` → 503/504 ile başlamadan düştü; 11:43'te `GET /api/v2/workspaces` da 504. Platform kesintisi, bizim kodla ilgisi yok. `queue15`: API cevap verene kadar bekler, B 3. koşuyu yeniden puanlar, çöken dört ölçümü sonuç satırı çıkana dek en çok 3 kez tekrarlar. Kesinti uzarsa 12:30 dondurma ölçümsüz kalır; karar o zaman: A v23 10/10 kanıtlı, değişiklik yalnız kapanış koruması.

## 11 Ekim, 11:43–11:52: kesinti sonrası: takılan simülasyon silindi, yetim simülasyonlar; B v18 ara sonuçlar

API 11:43'te geri geldi, `queue15` kendiliğinden devam etti. `ebea0e47` (B 3. koşu) "running"de takıldı (PUB-13 kaydı gelmedi; PUB-11, PUB-12 PASS); İhsan panelden sildi. Platform kesinti sırasında `POST /api/v2/simulations` hata dönerken simülasyonu yine yarattı: run_cases kendi açtığı simülasyonu "başka simülasyon çalışıyor" diye bekledi (`437e83a6` "cases 11:43:58", sonra `ffb81d49` "cases 11:47:40"). Bunlar tamamlanınca kuyruk ilerliyor. `437e83a6` yeniden puanlandı (own-b-2): **3/3**. B v18 şu ana kadar: `--brief B` koşu 1 3/3, koşu 2 3/3, koşu 3 2/2 (PUB-13 kayıp); own-b-2 ek koşu 3/3.

## 11 Ekim, 11:43–12:27: kendi vakalar A v23 / B v18; **12:30 dondurma: `4f64795` skill'i**

Hepsi `--reps 3` (kesinti sonrası `queue15`; own-b-2 ve own-a-1 ilk denemeleri 502 ile çöktü, yeniden koşuldu):
- own-a-2 (A v23): **10/10** (10, 10, 10). v22: 10/10.
- own-a-1 (A v23): **7/10** (koşular 7, 9, 8; 24/30). v22: 7/10 (21/30). PUB-09 (geri arama koruması) **3/3** (v22 0/3). PUB-02 1/3: düzeltilmiş kontrolle judge tabanı kabul etti; kalmalar söz kaydedilmemesi (kesik müşteri cümleleri). PUB-05 0/3 (bilinen, "iki kez konuşmak istemiyorum"). PUB-10 1. koşu: `create_promise` servis hatasından sonra tekrar denenmedi (yavaş koşu, 478 sn); 2/3. Çöken ilk denemenin tek koşusu (`6970a1ac`) 9/10.
- own-b-2 (B v18): **2/3** (koşular 2, 3, 2; 7/9) + yetim simülasyon `437e83a6` 3/3. PUB-12 2 koşu: müşterinin "bu Cumartesi"si için araba kredisi 16 Ekim (Cuma) kaydedildi, beklenen 19 Ekim (Pazartesi). v17: 3/3 (9/9).
- own-b-1 (B v18): **1/3** (koşular 2, 2, 3; 7/9). v17 aynı (7/9). PUB-11 1 koşu ret sonrası taksit teklifi, PUB-13 1 koşu ürünler arası tarih (27/16 yerine 28/23).
- Organizatör: A v23 **10/10** (30/30, yeniden puanla), B v18 koşular 3/3, 3/3, 2/2 (PUB-13 kesintide kayıp; 8/8).
Karşılaştırma (skill farkı yalnız kapanış koruması): A tarafında her dosya eşit ya da daha iyi; B'de organizatör 8/9 → 8/8, own-b-1 aynı, own-b-2 9/9 → 7/9 (tarih ailesi; skill değişikliği tarihe dokunmuyor, build'den build'e oynama). **Karar: `4f64795` skill'i ile donuldu** (durma kuralı: A ≥ 9/10, B ≥ 2/3, gerileme yok). Açık aileler, mekanizmasız: ürünler arası tarih, ürün başına deneme sayısı, "iki kez konuşmak istemiyorum", servis hatası sonrası tekrar deneme (1 koşu). `queue16` (genelleme: ham A, I, G, H, C, D; E ve F yalnız build) başlatıldı.

## 11 Ekim, 12:30–12:55: own-b-2 PUB-12 tarih hatasının okunması; genelleme kuyruğu kesintide

**Tarih hatası (B v18, own-b-2 PUB-12, koşu 1 ve 3):** ajan "bugün"ü biliyor (`now` = 14 Ekim Çarşamba) ve tarihi kendisi hesaplamıyor; ürün başına gün tablosu prompt'ta. Aynı kodla yerelde üretilen tablo: "the 17th = Saturday 17 October: weekend, not a business day -> use Monday 19 October instead", 16 ve 19 "business day, can be used", 24'ten sonrası "AFTER the latest date". Ajan Cumartesi'ye Pazartesi 19'u önerdi, kartı 19'a doğru kaydetti; araba kredisini 16 Ekim'e (o ürünün satırındaki 1. deneme tarihi, müşterinin kabul etmediği) kaydetti. 3. koşuda judge ayrıca ajanın "Saturday 18 October" dediğini yazdı (tablo 17 diyor). `create_promise` tarih koruması (bugün ≤ tarih ≤ son tarih, iş günü) 16'yı geçerli saydı; kodun "müşterinin onayladığı tarih" bilgisi yok. Çağrı dökümleri (`b6a46d86…`, `c324400d…`) Freya `GET /api/v2/call` 504 yüzünden okunamadı; bulgu kayıt ve judge notundan.
**Neden Pazartesi (İhsan sordu):** Brief A kural 20 "hafta sonu ya da tatil → bir sonraki iş günü", yani adı geçen günden sonraki ilk iş günü; Perşembe 15 / Cuma 16 müşterinin istediğinden erken. Organizatör PUB-07 aynı yorumu doğruluyor (tatil 26 → 27 beklenir). Yön builder'da brief'ten okunan ayar (`"shifts": "forward" | "backward"`); Brief I'da tersi (önceki iş günü) ve I öyle kuruldu.
**Genelleme kuyruğu (`queue16`):** ham A build'i 12:28–12:34, çıkış 0 (agent `e450b416…`, workflow `brief-a-raw`). Ölçüm `--brief A` iki kez `POST /api/v2/simulations` 504 ile başlayamadı (12:38, 12:45); kuyruk API'nin dönmesini bekliyor, sonra 3. deneme ve I, G, H, C, D, E/F. Ölçülmedi: hiçbiri. Kuyruk I, G, H, E, F için 5 yeni workflow açacak (toplam 11); bitince pratik workflow'lar panelden silinmeli. Commit'e A v23 ve B v18 build trace'leri (`submission/brief-{a,b}.trace.log`, gizli taraması 0) eklendi; `submission/brief-a-raw.*`, `brief-g.workflow.json` ve kökteki brief-c…h.md pratik dosyaları commit dışı, 16:00 temizliğinde ele alınacak.

## 11 Ekim, 13:00–13:20: ham A ölçümü üç denemede de kesintiye düştü; ikinci Freya kesintisi

`yc-builder-20261011-1258.zip` repo kökünde (İhsan aldı; `.venv`, `env.sh`, önbellekler hariç, anahtar taraması 0; commit dışı). Ham A ilk ölçüm simülasyonu `1378c096` ("cases 12:34:23") judge kararsız kaldığı için 34 dk "running"de takıldı; yeniden puanla: PUB-06 FAIL (taban iki kez, bilinen), PUB-02 ve PUB-05 judge metni "hepsi sağlandı" ama inconclusive, diğerlerinin kaydı eksik. İhsan sildi. Platform 13:06'daki POST'u yine yetim simülasyon olarak açtı (`f9bf1312`, "cases 13:06:01"); 13:16'da Freya tekrar 503/504'e düştü, yeniden puanlama yapılamadı. Ham A için `queue16`'nın 3 denemesi bitti, kuyruk API dönünce I'ya geçer. `queue17`: API dönünce `f9bf1312`'yi yeniden puanlar, `queue16`'dan sonra ham A'yı yeniden ölçer. Ölçülmedi: ham A (hiç tam koşu yok).

## 11 Ekim, 13:18–13:40: I build'i, ölçüm aracı GET'leri tekrar deniyor (`dev/run_cases_retry.py`)

I build'i 13:18–13:27, çıkış 0 (agent `712a168e…`). İhsan yetim ham A simülasyonunu (`f9bf1312`, 8 çağrının hiçbiri bitmemiş) sildi. I ölçümü 13:27'de başladı (`cc44ad7c`, Freya'da çalışıyor), ama run_cases durum sorgusunda tek bir 503 ile düştü; kuyruk yeniden denemeyi o simülasyonun arkasında bekletiyor. Düzeltme (yalnız ölçüm aracı; ajan ve kit dosyası değişmedi): `dev/run_cases_retry.py`, kit'in `run_cases.py`'sini `freya.api`'de GET isteklerini 502/503/504'te 15, 30, 60, 120 sn arayla tekrar deneyerek çalıştırır; POST tekrarlanmaz (başarısız görünen POST simülasyonu yine yaratabiliyor). Kuyruğun `step.sh`'i artık bunu kullanıyor; meşguliyet denetimi iki süreç adını da görüyor. Sahte `_api` ile denendi (GET iki 503'ten sonra geçti, POST tekrar edilmedi). Testler 546 yeşil.

## 11 Ekim, 13:40–14:15: üçüncü Freya kesintisi; G build'i kaydedildi ama export düştü; kuyruk betiği çıkış kodu hatası

I ölçümü üç denemede de kesintiye denk geldi (13:31 denemesi 16 dk simülasyonu bekleyip düştü; 13:49 POST 504). G build'i 13:50–14:10 (1195 sn, $1,96, 27 tur): builder 504'lere karşı `builder.save`'i kendisi döngüyle 4 kez denedi; slot `brief-g` Freya'da kayıtlı (workflow `0006405b…`, agent `7a31caf4…`, `version` alanı yok), ama `[export] FAILED: GET /api/v2/workspaces -> 504`. build.py doğru çalıştı (export düşünce 1 döner, `build.py:352`); kuyruk betiği `step.sh` `echo "[$(date)] ... exit $?"` yazdığı için `$?` `date`'in kodunu gösteriyordu: **kuyruk günlüğündeki bütün "build exit 0" satırları güvenilmez** (önceki build'lerin trace'lerinde `[export] wrote` var, onlar sağlam). Düzeltildi (`rc=$?`).
Kökteki `brief-d.md` slotu `brief-d` değil `brief-d-518c5c` (aynı ad, farklı içerik → hash'li slot, `slot_for`); eski kuyruk D'yi yanlış ajanla ölçecekti. `queue16`/`queue17` durduruldu; yerine `queue18`: her adımdan önce API'yi bekler, `[export] wrote` olmayan build'i yeniden build etmeden `builder.save` ile yeniden kaydeder (5 deneme), ölçümleri 3 kez dener; sıra: I yeniden puanla (`cc44ad7c`) + ölç, G kaydet + G kendi + B, H, C, D (`brief-d-518c5c`), ham A, E, F.
**Bu akşam için ders:** gizli brief koşusunda Freya düşerse ajan ve `gen.py` yerelde hazır kalır; build'i tekrarlamadan `python3 -m builder.save <slot> builder/work/<slot>/workflow.json <değişkenler>` ile kaydedilir, export için build.py'nin `export` adımı (ya da `freya.export_workflow`) ayrıca koşulur. Kayıt durumu `builder/work/.freya-agents.json`'da.

## 11 Ekim, 15:05: karar: akşam build'leri Claude Code girişiyle, `ANTHROPIC_API_KEY` provası yok

İhsan: "şuanki durum iyi, key'e gerek yok". Gizli brief build'leri bu makinede Claude Code girişiyle koşulacak (bugünkü bütün build'ler böyle; trace `[setup] Claude access: no ANTHROPIC_API_KEY, using this machine's Claude Code login`). Ölçülmedi: `ANTHROPIC_API_KEY` ile build (organizatör yeniden koşarsa bu yol denenmemiş). Freya API 15:03'te hâlâ arada 503/504 veriyor; I ölçümü (`ea22ed90`, 14:52) `run_cases_retry` ile sürüyor.
