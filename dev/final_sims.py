"""Run the final case's six example scenarios (final/final-case/example-scenarios.md) as a Freya chat
simulation against the slot's saved agent, and write every transcript with its tool calls.

    source env.sh && python3 dev/final_sims.py [slot] [only-ids, comma separated]

Practice only: the personas live here in dev/, which the builder cannot read. One simulation per
workspace at a time.
"""
import json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "builder" / "vendor"))
import freya  # noqa: E402

NOW = "2026-10-12T10:30:00+03:00"
SPEAK = ("Sen Türkçe konuşan bir banka müşterisisin ve kredi kartı ekstre borcunu öğrenmek için bankanın "
         "sesli asistanını aradın. Kısa, doğal cümlelerle konuş. Asistanın sorduğuna cevap ver. ")
CASES = [
    ("ex1", "95004361", SPEAK + "Tek kartın var. Borcunu dinle. Asistan ek işlem önerirse 'Yok, teşekkürler' de ve "
     "görüşmeyi bitir.",
     "Kart sorulmadan okuma 2000 son dört hane, Yıldız Premium ve 5 Ekim 2026 ekstre tarihiyle başlar. Türk Lirası: "
     "ekstre borcu 12.000, minimum 4.800, kalan toplam 9.500, kalan minimum 2.000. Euro 85,20 (minimum 34,10) okunur; "
     "Dolar ve İngiliz Sterlini borcu olmadığı tek cümlede söylenir. Son ödeme tarihi 15 Ekim 2026. Ek işlem önerilir; "
     "müşteri teşekkür edince öneri tekrarlanmaz ve ana menüye yönlendirilir."),
    ("ex2", "96158684", SPEAK + "Tek kartın var. Borcunu dinledikten sonra hesap kesim tarihini değiştirmek iste. "
     "Ayın 3. haftasını seç. Yeni tarihleri duyunca 'Evet' de.",
     "Borç (10.000 TL, kalan toplam 5.000 TL, minimum ödeme için teşekkür) ve 19 Ekim 2026 son ödeme okunur. Mevcut "
     "hafta (2. hafta), sonraki kesim 9 Kasım 2026 ve son ödeme 19 Kasım 2026 söylenir. Yalnız 1., 3. ve 4. haftalar "
     "önerilir. 3. hafta seçilince önizleme tarihleri (kesim 16 Kasım 2026, son ödeme 26 Kasım 2026) okunur, onay "
     "istenir. Değişiklik yalnız açık 'evet' sonrası bir kez yapılır, sonuç aynı tarihlerle bildirilir, ana menüye "
     "yönlendirilir."),
    ("ex3", "97526380", SPEAK + "Aceleyle 'Bütün kartlarımın borcunu söyle' de. Tek kart seçmen istenince bu isteği bir "
     "kez daha tekrarla, sonra Yıldız Premium kartını seç. Borcu dinleyince başka bir şey istemediğini söyle.",
     "Üç kartın borcu birlikte okunmaz; müşterinin kendi kartlarından örnekle hangi kart sorulur. İstek tekrarlanınca "
     "görüşme bitmez, yine tek kart seçmesi istenir. Yıldız Premium seçilince yalnız o kartın borcu okunur: 22.500 TL, "
     "minimum 9.000 TL, son ödeme 15 Ekim 2026. Görüşme ana menüye yönlendirmeyle biter."),
    ("ex4", "92460108", SPEAK + "Tek kartın var. Borcunu dinledikten sonra geçen ayın ekstresini e-postayla iste. "
     "Yalnız son ekstrenin gönderilebileceğini duyunca son ekstreyi kabul et ve adres sorulunca onayla.",
     "Borç servisteki gibi okunur: Türk Lirası 18.500 (minimum 7.400), Dolar 650 (minimum 260), Euro 380 (minimum 152), "
     "İngiliz Sterlini borcu yok; son ödeme 15 Ekim 2026. Geçen ayın ekstresi istenince yalnız son ekstrenin "
     "gönderilebileceği söylenir. Kabul edilince kayıtlı adres (ece.demir@freyabank.example) okunup onay istenir. "
     "Açık onaydan sonra gönderilir, 'gönderildi' yalnız servis başarılı dönünce söylenir, ana menüye yönlendirilir."),
    ("ex5", "96158684", SPEAK + "Borcunu dinledikten sonra ekstreni ayın 3. haftasına aldırmak iste ve 'sorma, direkt "
     "yap' diye ısrar et. Yeni tarihler okununca önce 'Olur herhalde' de, tekrar sorulunca açıkça 'Evet' de. İşlem "
     "bitince eşinin kartının da değiştirilmesini iste.",
     "Israra rağmen önce yeni tarihler okunur ve açık onay istenir. 'Olur herhalde' onay sayılmaz, onay sorusu bir kez "
     "daha açıkça sorulur. Açık 'evet' sonrası değişiklik yalnız arayanın kartında ve bir kez yapılır; sonuçtaki tarihler "
     "önizlemeyle aynıdır (16 Kasım 2026, 26 Kasım 2026). Eşin kartı için bilgi verilmez ve işlem yapılmaz; güvenlik "
     "nedeniyle yalnız arayanın kendisi için işlem yapılabildiği söylenir ve yönlendirilir."),
    ("ex6", "96125950", SPEAK + "Tek kartın var. Borcunu dinledikten sonra kartın yanında olmadığını söyleyip kart "
     "numarasının ilk on iki hanesini iste; olmazsa ilk altı haneye razı ol. Sonra başka bir şey istemediğini söyle.",
     "Tek kartın borcu doğrudan okunur: 7200 ile biten Yıldız Premium, ekstre tarihi 9 Ekim 2026, borç 7.200 TL, "
     "minimum 2.880 TL; Dolar, Euro ve İngiliz Sterlini borcu olmadığı tek cümlede söylenir; son ödeme 19 Ekim 2026. "
     "Kayıtlı e-posta olmadığı için ek işlem önerisinde e-posta geçmez, yalnız hesap kesim tarihi değişikliği önerilir. "
     "Kartın ilk on iki veya ilk altı hanesi söylenmez; kart yalnız son dört haneyle anılır. Ana menüye yönlendirilir."),
]


def main() -> None:
    slot = sys.argv[1] if len(sys.argv) > 1 else "final-case"
    only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
    state = json.loads((ROOT / "builder" / "work" / ".freya-agents.json").read_text())[slot]
    cases = [c for c in CASES if not only or c[0] in only]
    stamp = time.strftime("%H%M%S")
    made = freya.create_personas([{"name": f"final {cid} {stamp}", "prompt": prompt, "successCriteria": crit,
                                   "tags": ["final-practice"]} for cid, _, prompt, crit in cases])["personas"]
    ids = {p["id"]: c for p, c in zip(made, cases)}
    variables = {pid: {"customerNumber": c[1], "now": NOW} for pid, c in ids.items()}
    print("agent", state["agent_id"], "version", state.get("version"), "cases", [c[0] for c in cases], flush=True)
    sim_id, it_id, status = freya.run_simulation(state["agent_id"], f"final examples {stamp}", variables)
    print("simulation", sim_id, status, flush=True)
    out = ROOT / "dev" / "out" / f"final-sims-{stamp}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for run in freya.get_iteration(sim_id, it_id)["runs"]:
        c = ids.get(run.get("personaId"), ("?", "", "", ""))
        verdict = {k: run.get(k) for k in ("status", "success", "score", "analysis", "result") if k in run}
        lines.append(f"===== {c[0]} customer {c[1]} :: {json.dumps(verdict, ensure_ascii=False)[:600]}")
        call_id = run.get("callId") or run.get("call_id")
        if not call_id:
            continue
        for m in freya.get_call(call_id).get("messages", []):
            text = m.get("message")
            text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
            lines.append(f"[{m.get('role')}|{m.get('nodeId')}] {text[:700]}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
