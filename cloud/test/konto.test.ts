import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, b64u, codeAnlegen, fernet, jsonVon, kontoAnlegen, neueIp, rufen, zufall } from "./hilfe";

const KDF = { name: "argon2id", t: 3, m: 65536, p: 4 };

describe("Konto anlegen", () => {
  it("legt an, verbraucht den Code, Mail klein", async () => {
    const code = await codeAnlegen();
    const body = {
      mail: "  Jemand@Example.ORG ", code, salz: b64u(zufall(16)), kdf: KDF,
      anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet(), verpackt_notfall: fernet(),
      notfall_beweis: b64u(zufall()),
    };
    const r = await rufen("POST", "/v1/konto", { json: body });
    expect(r.status).toBe(201);
    expect((await jsonVon(r)).mail).toBe("jemand@example.org");

    const row = await env.DB.prepare("SELECT hash_art, anmelde_hash, anmelde_salz, notfall_hash FROM konten WHERE mail = ?")
      .bind("jemand@example.org").first<{ hash_art: string; anmelde_hash: string; anmelde_salz: string; notfall_hash: string }>();
    expect(row?.hash_art).toBe("hmac-sha256");
    expect(row?.anmelde_hash).not.toBe(body.anmelde_schluessel);
    expect(row?.anmelde_hash).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(row?.anmelde_salz).toMatch(/^[A-Za-z0-9_-]{43}$/); // 32 bytes

    // Code ist verbraucht.
    const zweit = await rufen("POST", "/v1/konto", { json: { ...body, mail: "anders@example.org" } });
    expect(zweit.status).toBe(403);
    expect((await jsonVon(zweit)).fehler).toBe("code_ungueltig");

    // Gleiche Mail (andere Schreibweise) mit neuem Code → 409.
    const doppelt = await rufen("POST", "/v1/konto", {
      json: { ...body, mail: "JEMAND@example.org", code: await codeAnlegen() },
    });
    expect(doppelt.status).toBe(409);
    expect((await jsonVon(doppelt)).fehler).toBe("mail_vergeben");
  });

  it("weist unbekannte Codes und kaputte Felder ab", async () => {
    const body = {
      mail: "x@example.org", code: "GIBTSNICHT", salz: b64u(zufall(16)), kdf: KDF,
      anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet(), verpackt_notfall: fernet(),
      notfall_beweis: b64u(zufall()),
    };
    expect((await rufen("POST", "/v1/konto", { json: body })).status).toBe(403);
    const ohneBeweis = { ...body, code: await codeAnlegen() } as Record<string, unknown>;
    delete ohneBeweis.notfall_beweis;
    expect((await rufen("POST", "/v1/konto", { json: ohneBeweis })).status).toBe(400);
    expect((await rufen("POST", "/v1/konto", { json: { ...body, kdf: { ...KDF, m: 1024 } } })).status).toBe(400);
    expect((await rufen("POST", "/v1/konto", { json: { ...body, anmelde_schluessel: "kurz" } })).status).toBe(400);
    expect((await rufen("POST", "/v1/konto", { json: { ...body, mail: "keine-mail" } })).status).toBe(400);
    expect((await rufen("POST", "/v1/konto", { body: "{kaputt", kopf: { "Content-Type": "application/json" } })).status).toBe(400);
    const gross = await rufen("POST", "/v1/konto", { json: { ...body, rest: "x".repeat(20_000) } });
    expect(gross.status).toBe(413);
    expect((await jsonVon(gross)).fehler).toBe("zu_gross");
  });
});

describe("Vorab", () => {
  it("liefert echte Werte für bekannte Mail", async () => {
    const k = await kontoAnlegen();
    const d = await jsonVon(await rufen("POST", "/v1/vorab", { json: { mail: k.mail.toUpperCase() } }));
    expect(d.salz).toBe(k.salz);
    expect(d.kdf).toEqual(KDF);
  });

  it("erfindet feste Werte für unbekannte Mail", async () => {
    const a1 = await jsonVon(await rufen("POST", "/v1/vorab", { json: { mail: "niemand@example.org" } }));
    const a2 = await jsonVon(await rufen("POST", "/v1/vorab", { json: { mail: "Niemand@Example.org" } }));
    const b = await jsonVon(await rufen("POST", "/v1/vorab", { json: { mail: "keiner@example.org" } }));
    expect(a1).toEqual(a2);
    expect(a1.salz).not.toBe(b.salz);
    expect(a1.kdf).toEqual(KDF);
    expect(a1.salz).toMatch(/^[A-Za-z0-9_-]{22}$/);
  });
});

describe("Sitzung", () => {
  it("meldet an und ab; Token nur als Hash gespeichert", async () => {
    const k = await kontoAnlegen();
    const r = await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: k.anmelde_schluessel, knoten: "minipc" },
    });
    expect(r.status).toBe(200);
    const d = await jsonVon(r);
    expect(d.verpackt_passwort).toBe(k.verpackt_passwort);
    expect(d.token).toMatch(/^[A-Za-z0-9_-]{43}$/);
    const tage = (Date.parse(d.laeuft_ab) - Date.now()) / 86_400_000;
    expect(tage).toBeGreaterThan(89.9);
    expect(tage).toBeLessThan(90.1);

    const roh = await env.DB.prepare("SELECT COUNT(*) AS n FROM sitzungen WHERE token_hash = ?").bind(d.token).first<{ n: number }>();
    expect(roh?.n).toBe(0);
    const s = await env.DB.prepare("SELECT knoten FROM sitzungen WHERE konto_id = (SELECT id FROM konten WHERE mail = ?)")
      .bind(k.mail).first<{ knoten: string }>();
    expect(s?.knoten).toBe("minipc");

    expect((await rufen("GET", "/v1/mitte", { token: d.token })).status).toBe(200);
    expect((await rufen("DELETE", "/v1/sitzung", { token: d.token })).status).toBe(200);
    expect((await rufen("GET", "/v1/mitte", { token: d.token })).status).toBe(401);
    expect((await rufen("DELETE", "/v1/sitzung", { token: d.token })).status).toBe(401);
  });

  it("falsches Passwort und unbekannte Mail sehen gleich aus", async () => {
    const k = await kontoAnlegen();
    const falsch = await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: b64u(zufall()), knoten: "laptop" },
    });
    const unbekannt = await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: "gibts-nicht@example.org", anmelde_schluessel: b64u(zufall()), knoten: "laptop" },
    });
    expect(falsch.status).toBe(401);
    expect(unbekannt.status).toBe(401);
    expect(await jsonVon(falsch)).toEqual(await jsonVon(unbekannt));
  });

  it("drosselt nach 5 Fehlversuchen je Mail", async () => {
    const k = await kontoAnlegen();
    for (let i = 0; i < 5; i++) {
      const r = await rufen("POST", "/v1/sitzung", {
        ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: b64u(zufall()), knoten: "laptop" },
      });
      expect(r.status).toBe(401);
    }
    // Auch mit dem richtigen Schlüssel und von einer neuen IP: gesperrt.
    const r = await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: k.anmelde_schluessel, knoten: "laptop" },
    });
    expect(r.status).toBe(429);
    expect((await jsonVon(r)).fehler).toBe("zu_viele_versuche");
    expect(Number(r.headers.get("Retry-After"))).toBeGreaterThan(0);

    // Nach Ablauf des Fensters geht es wieder.
    await env.DB.prepare("UPDATE drossel SET start = start - 16 * 60 * 1000").run();
    expect(await anmelden(k)).toBeTruthy();
  });

  it("drosselt nach 5 Fehlversuchen je IP", async () => {
    const ip = "192.0.2.77";
    for (let i = 0; i < 5; i++) {
      await rufen("POST", "/v1/sitzung", {
        ip, json: { mail: `raten${i}@example.org`, anmelde_schluessel: b64u(zufall()), knoten: "laptop" },
      });
    }
    const k = await kontoAnlegen();
    const r = await rufen("POST", "/v1/sitzung", {
      ip, json: { mail: k.mail, anmelde_schluessel: k.anmelde_schluessel, knoten: "laptop" },
    });
    expect(r.status).toBe(429);
  });
});

describe("Notfall und Passwort", () => {
  it("Notfallschlüssel → neues Passwort; alte Sitzungen enden", async () => {
    const k = await kontoAnlegen();
    const alt = await anmelden(k);

    const falsch = await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { mail: k.mail, notfall_beweis: b64u(zufall()) } });
    expect(falsch.status).toBe(401);
    expect((await jsonVon(falsch)).fehler).toBe("falscher_notfallschluessel");

    const r = await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { mail: k.mail, notfall_beweis: k.notfall_beweis } });
    expect(r.status).toBe(200);
    const d = await jsonVon(r);
    expect(d.verpackt_notfall).toBe(k.verpackt_notfall);

    // Die Notfall-Sitzung darf nur das Passwort setzen.
    const verboten = await rufen("GET", "/v1/mitte", { token: d.token });
    expect(verboten.status).toBe(403);
    expect((await jsonVon(verboten)).fehler).toBe("nur_passwort");

    const neu = { salz: b64u(zufall(16)), kdf: KDF, anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet() };
    expect((await rufen("PUT", "/v1/konto/passwort", { token: d.token, json: neu })).status).toBe(200);

    // Alles Alte ist abgemeldet, auch die Notfall-Sitzung.
    expect((await rufen("GET", "/v1/mitte", { token: alt })).status).toBe(401);
    expect((await rufen("PUT", "/v1/konto/passwort", { token: d.token, json: neu })).status).toBe(401);

    // Alter Schlüssel geht nicht mehr, neuer schon; vorab liefert das neue Salz.
    const altLogin = await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: k.anmelde_schluessel, knoten: "laptop" },
    });
    expect(altLogin.status).toBe(401);
    const neuLogin = await jsonVon(await rufen("POST", "/v1/sitzung", {
      ip: neueIp(), json: { mail: k.mail, anmelde_schluessel: neu.anmelde_schluessel, knoten: "laptop" },
    }));
    expect(neuLogin.verpackt_passwort).toBe(neu.verpackt_passwort);
    expect((await jsonVon(await rufen("POST", "/v1/vorab", { json: { mail: k.mail } }))).salz).toBe(neu.salz);

    // Der Notfallschlüssel selbst bleibt gültig.
    expect((await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { mail: k.mail, notfall_beweis: k.notfall_beweis } })).status).toBe(200);
  });

  it("Notfall wird gedrosselt", async () => {
    const k = await kontoAnlegen();
    for (let i = 0; i < 5; i++) {
      await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { mail: k.mail, notfall_beweis: b64u(zufall()) } });
    }
    const r = await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { mail: k.mail, notfall_beweis: k.notfall_beweis } });
    expect(r.status).toBe(429);
  });

  it("Passwort ändern mit normaler Sitzung: altes nötig, diese bleibt, andere enden", async () => {
    const k = await kontoAnlegen();
    const andere = await anmelden(k, "pc");
    const diese = await anmelden(k, "laptop");
    const neu = { salz: b64u(zufall(16)), kdf: KDF, anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet() };
    // Ohne oder mit falschem altem Schlüssel geht nichts.
    expect((await rufen("PUT", "/v1/konto/passwort", { token: diese, json: neu })).status).toBe(400);
    const falsch = await rufen("PUT", "/v1/konto/passwort", { token: diese, json: { ...neu, altes_anmelde_schluessel: b64u(zufall()) } });
    expect(falsch.status).toBe(401);
    expect((await jsonVon(falsch)).fehler).toBe("falsche_anmeldung");
    expect((await rufen("GET", "/v1/mitte", { token: andere })).status).toBe(200);

    const ok = await rufen("PUT", "/v1/konto/passwort", { token: diese, json: { ...neu, altes_anmelde_schluessel: k.anmelde_schluessel } });
    expect(ok.status).toBe(200);
    expect((await rufen("GET", "/v1/mitte", { token: diese })).status).toBe(200);
    expect((await rufen("GET", "/v1/mitte", { token: andere })).status).toBe(401);
    expect((await rufen("PUT", "/v1/konto/passwort", { json: neu })).status).toBe(401);
  });

  it("Passwort ändern wird gedrosselt", async () => {
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    const neu = { salz: b64u(zufall(16)), kdf: KDF, anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet() };
    for (let i = 0; i < 5; i++) {
      const r = await rufen("PUT", "/v1/konto/passwort", { token: t, ip: neueIp(), json: { ...neu, altes_anmelde_schluessel: b64u(zufall()) } });
      expect(r.status).toBe(401);
    }
    const r = await rufen("PUT", "/v1/konto/passwort", { token: t, ip: neueIp(), json: { ...neu, altes_anmelde_schluessel: k.anmelde_schluessel } });
    expect(r.status).toBe(429);
  });
});

describe("Allgemein", () => {
  it("kein CORS, unbekannte Wege 404, falsche Methode 405", async () => {
    const r = await rufen("GET", "/v1/vorab");
    expect(r.status).toBe(405);
    expect(r.headers.get("Allow")).toBe("POST");
    expect((await rufen("OPTIONS", "/v1/sitzung", { kopf: { Origin: "https://evil.example" } })).headers.get("Access-Control-Allow-Origin")).toBeNull();
    const nichts = await rufen("GET", "/v2/irgendwas");
    expect(nichts.status).toBe(404);
    expect(await jsonVon(nichts)).toEqual({ fehler: "nicht_gefunden", text: expect.any(String) });
  });
});
