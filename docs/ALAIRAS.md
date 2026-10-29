# Kódaláírás beállítása (SignPath Foundation)

Aláírás nélkül a Windows SmartScreen figyelmeztet, az Intelligens alkalmazásvezérlés (Smart App
Control) pedig le is tiltja az appot. A SignPath Foundation nyílt forrású projekteknek ingyen ad
kódaláíró tanúsítványt; kiadóként a „SignPath Foundation” jelenik meg. Azonnali SmartScreen-bizalmat
ez sem ad, az a letöltésekkel épül fel, de a teljes tiltás megszűnik.

## 1. Előfeltételek (neked kell)

- Kétlépcsős azonosítás a GitHub-fiókodon (Settings → Password and authentication).
- Az aláírási szabályzat ([CODE_SIGNING_POLICY.md](../CODE_SIGNING_POLICY.md)) a `main` ágon van,
  és a README-ből és minden kiadásból link mutat rá; ez kész.

## 2. Jelentkezés

A <https://signpath.org/apply> oldalon. Hasznos válaszok:

- **Projekt:** GameBooster, <https://github.com/AdamDruszad/pc-optimizer>, MIT-licenc.
- **Mit csinál:** Windows-optimalizáló játékosoknak; minden rendszermódosítást megerősítés után,
  változásnaplóval végez, és bármikor visszaállít. Nincs telemetria.
- **Build:** GitHub Actions (`release.yml`), PyInstaller + Inno Setup; a kiadásokat egy verziótag
  indítja.
- **Aláírandó fájlok:** `GameBooster.exe`, `GameBooster-Setup-x.y.z.exe`.

## 3. SignPath-oldali beállítás (elfogadás után)

A workflow ezeket a neveket (slug) várja; ha mást választasz, a `release.yml`-ben is írd át.

- **Projekt:** `gamebooster`; a GitHub-repó mint megbízható build-rendszer.
- **Aláírási szabályzat (signing policy):** `release-signing`, kézi jóváhagyással.
- **Artifact configuration `app`** (a feltöltött mappa zip-ként érkezik; csak a saját exe kerül
  aláírásra, a Python/Tcl/psutil fájlok a kiadójuk aláírásával maradnak):

  ```xml
  <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
    <zip-file>
      <pe-file path="GameBooster.exe" product-name="GameBooster">
        <authenticode-sign />
      </pe-file>
    </zip-file>
  </artifact-configuration>
  ```

- **Artifact configuration `installer`:**

  ```xml
  <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
    <zip-file>
      <pe-file path="GameBooster-Setup-*.exe" product-name="GameBooster">
        <authenticode-sign />
      </pe-file>
    </zip-file>
  </artifact-configuration>
  ```

  Az XML-sémát a SignPath felületén ellenőrizd; ezek a minták a dokumentáció alapján készültek, éles
  SignPath-projekten nincsenek kipróbálva.

## 4. GitHub-beállítás

Repó → Settings → Secrets and variables → Actions:

- **Variable** `SIGNPATH_ORGANIZATION_ID`: a SignPath-szervezeted azonosítója.
- **Secret** `SIGNPATH_API_TOKEN`: egy beküldő (submitter) jogú SignPath-felhasználó API-tokenje.

Amíg ezek nincsenek beállítva, a `release` workflow kihagyja az aláírási lépéseket, és aláíratlanul
ad ki, ugyanúgy, mint eddig. Beállítás után a következő verziótagnél az aláírás magától megtörténik
(minden kérést jóvá kell hagynod a SignPath felületén).

## Addig is

- Minden kiadás után beküldheted a `Setup.exe`-t a Microsoftnak téves riasztásként:
  <https://www.microsoft.com/en-us/wdsi/filesubmission> („Software developer” → „Incorrectly
  detected as malware/malicious”). Ez a Defender-riasztásokon segít, a SmartScreenen nem.
- A felhasználóknak a SmartScreen ablakában: „További információ → Futtatás mindenképp”. Ha a
  gépen be van kapcsolva az Intelligens alkalmazásvezérlés, aláírás nélkül nincs megoldás.
