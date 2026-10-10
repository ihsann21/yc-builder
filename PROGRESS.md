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

## Kararlar

- **Yol B (karma):** kit'in ajan tabanlı builder'ı temel; üstüne bizim skill'lerimiz ve test edilmiş yardımcı kod parçalarımız (tarih ve iş günü, ürün başına son tarih ve geri okuma, deneme sayaçları, deterministik `close_call` sonucu, "sırada ne var" kancaları). Planın ağır kısımları (AgentSpec, iki sağlayıcı, τ vekil benchmark) kullanılmıyor; plan akşam sadeleştirilecek.
- **Düzeltme kuralı:** düzeltme brief'e değil mekanizmaya yapılır; brief değeri (tatil, tutar, sonuç adı) koda yazılmaz.
- **Genelleme testi, sınırlı:** 1 biçim mutasyonu (Brief A ham malzeme biçiminde: e-posta, politika alıntısı, memo, kod listesi; beklenen sonuçlar aynı) + 2–3 kural mutasyonu (aynı 13 müşteri, farklı kurallar, beklenen sonuçlar elle). Müşteri verisi bankada sabit; kimlik soruları ve görüşme tarihi değiştirilemez.

## Açık sorular (destek kanalı)

19: ilk 10'un yeniden koşusunda builder'ın Claude anahtarını kim veriyor? · 23: gizli brief'lerin tool API'si pratik bankayla uyumlu mu, build sırasında test oturumu açılabiliyor mu? · 24: workflow sınırı 10 mu (site), 200 mü (kit README)?

## Kayıtlar

- Freya workflow'ları: `base` 0a1a92e1…, `brief-b` e6772bee… (agent 28027619…), `brief-a` 270d0e30… (agent 68a8b1f8…). Yerel eşleme: kit'te `.freya-agents.json`.
- Sonuçlar: kit'te `results/` (`base-A.json`, `b0-B-reps3.json`, `b0-A-reps3.json`, `b0-builder*.log`, `log.jsonl`). Trace'ler: `traces/` (anahtar içeriyor, paylaşılmaz).
- Commit edilmemiş: plan v1.4–1.5, kit klasörü, `scripts/`, bu dosya.

## Sıradaki

1. Kit builder'ının iki üretici betiğini ve workflow'larını okuyup ortak çekirdeği çıkarmak.
2. `builder/` iskeleti: `build.py` (tek komut, 25 dk sınırı, temiz trace, export), skill'ler, yardımcı kitaplık.
3. Gizli brief provası: test cevaplarına erişimi olmayan builder + ham malzeme biçiminde Brief A. Stil testleri (`--style pieces`, `in_words`).
4. Akşam: planı yeni yola göre sadeleştirmek.
