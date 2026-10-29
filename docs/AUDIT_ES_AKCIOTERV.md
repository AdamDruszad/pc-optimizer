# GameBooster (pc-optimizer): audit és akcióterv

- **Dátum:** 2026-10-29
- **Vizsgált állapot:** `main` @ `0f7c1e7`, 18 Python fájl, kb. 5500 sor
- **Módszer:** teljes kódolvasás, a gyanús pontok élő ellenőrzése ezen a gépen (Windows 11 26300, hu-HU), csak olvasó parancsokkal. Semmilyen boost vagy tweak nem futott.
- **Állapot:** javaslat. A 4. fázist (implementáció) csak a jóváhagyásod után kezdem.

---

## 0. Vezetői összefoglaló

1. **A visszaállítás nem megbízható.** Egy második Boost vagy registry-alkalmazás felülírja az eredeti értékeket a már módosítottakkal, így a „Visszaállítás” a módosított állapotot állítja vissza. A késleltetett indítású szolgáltatások (pl. `WSearch`) visszaállítás után „Kézi” típusúak lesznek. Ezt ezen a gépen ellenőriztem.
2. **Az app beleegyezés nélkül módosít.** Laptopon töltőre dugáskor automatikusan Boostol, a profil „Auto restore: igen” mezője pedig semmit nem csinál: kilépés után a Windows Update letiltva marad.
3. **A funkciók egy része placebo vagy káros.** A „RAM tisztítás” (EmptyWorkingSet minden folyamatra) akadást okoz, és kitalált „felszabadított MB” számot ír ki. Három MMCSS-értéket a Windows a Microsoft dokumentációja szerint figyelmen kívül hagy vagy felülír.
4. **A monitor maga terheli a gépet.** Kétmásodpercenként indít egy PowerShell-folyamatot (egyetlen GPU-counter lekérdezés ezen a gépen 1,7 s), a hőmérséklet pedig `wmic`-re épül, ami a gépen nincs telepítve, így mindig „N/A”.
5. **Architektúra:** egy 1580 soros GUI-osztály keveri a UI-t és a logikát, két holt modul (közel 720 sor) és egy véletlenül commitolt 23 MB-os kódkivonat (`osszes_kod.txt`) van a repóban, teszt nincs.

**Javasolt sorrend:** (4a) kis, célzott biztonsági hotfix a mostani kódon → (4b) közös változásnapló + tesztek → (4c) modulok átköltöztetése → (4d) új, valódi hatású funkciók → (4e) új UI-keret → (4f) takarítás és build.

---

## 1. FÁZIS: Kódbázis-audit

### 1.1 Struktúra és függőségek

```
main.py  (logging, sys.path, GameBoosterApp indítása)
└── gui/app.py  (GameBoosterApp, 7 fül, minden eseménykezelő)
    ├── gui/app_paths.py      írható útvonalak (exe mellé)
    ├── gui/sparkline.py      Canvas alapú vonaldiagram
    ├── modules/hardware_detector.py  WMI (PowerShell) + psutil, hw_monitor szál
    ├── modules/profile_manager.py    beépített + egyéni profilok (JSON)
    ├── modules/hw_optimizer.py       Boost / Restore (sc.exe, powercfg, ctypes)
    │   └── utils/state_manager.py    szolgáltatás-állapot mentése (original_state.json)
    ├── modules/ram_cleaner.py        EmptyWorkingSet, prioritás (ctypes)
    ├── modules/monitor.py            psutil + wmic hőmérséklet, system_monitor szál
    ├── modules/igpu_monitor.py       PowerShell Get-Counter, igpu_monitor szál
    └── modules/registry_tweaks.py    8 tweak + registry_snapshot.json

Holt (sehonnan nem importált): modules/registry_optimizer.py, modules/windows_optimizer.py,
main.spec, main.request_admin(), osszes_kod.txt (23 MB, UTF-16, pip forrásokkal együtt)
```

Két független alkalmaz/visszaállít folyamat van, két külön állapotfájllal (`original_state.json`, `registry_snapshot.json`). Közös „mindent visszaállít” nincs.

### 1.2 Kritikus hibák (adatvesztés, visszafordíthatatlan rendszerállapot)

| # | Hiba | Hely | Következmény |
|---|---|---|---|
| K1 | **A mentés minden alkalmazásnál felülíródik.** `save_original_state()` feltétel nélkül újraírja a fájlt; a registry-modul a meglévő snapshot szekcióit a már tweakelt értékekkel írja felül. | `utils/state_manager.py:68-78`, `modules/hw_optimizer.py:178`, `modules/registry_tweaks.py:572`, `:187`, `:228`, `:472`, `:530` | A második Boost után a mentésben `DISABLED` áll, a Restore nem kapcsolja vissza a szolgáltatásokat. A registry-restore a tweakelt értéket „állítja vissza”. |
| K2 | **A mentett és a módosított szolgáltatások listája eltér.** A mentés a fix `TARGET_SERVICES` 7 elemét rögzíti, a Boost a profil `stop_services` listáját tiltja le. | `utils/state_manager.py:27`, `modules/hw_optimizer.py:191` | Egyéni profilban felvett bármely más szolgáltatás végleg letiltva marad, a Restore nem tud róla. |
| K3 | **A késleltetett automatikus indítás elvész.** Az `sc qc` sor utolsó szavát olvassa, ami `(DELAYED)`, a leképezés ezt `demand`-ra (Kézi) fordítja. Ellenőrizve: `sc qc WSearch` → `AUTO_START (DELAYED)`. | `utils/state_manager.py:45-47`, `modules/hw_optimizer.py:81` | `WSearch`, `MapsBroker` visszaállítás után Kézi indításúak. |
| K4 | **A Restore hiba esetén is törli a mentést.** | `modules/hw_optimizer.py:249`, `modules/registry_tweaks.py:694` | Részleges hiba után nincs második próbálkozás. |
| K5 | **Az „Auto restore” csak felirat.** Az `auto_restore_on_exit` mezőt semmi nem olvassa, a `destroy()` csak a szálakat állítja le. | `modules/profile_manager.py:89`, `gui/app.py:1576-1580` | A felhasználó azt hiszi, kilépéskor minden visszaáll. A Windows Update és a többi szolgáltatás letiltva marad. |
| K6 | **Automatikus Boost beleegyezés nélkül.** Töltő csatlakoztatásakor a GUI magától Boostol. A `hw_monitor` első ciklusa mindig „változást” lát (`last_power = UNKNOWN`). | `gui/app.py:878-883`, `modules/hardware_detector.py:440`, `:464-466` | App-újraindítás után (a `_boost_active` jelző nem perzisztens) egy töltőre dugás újra Boostol, és K1 miatt felülírja az eredeti állapotot. |
| K7 | **A Gaming és az Akku profil letiltja a Windows Update-et** (`wuauserv`) és a biometrikus szolgáltatást (`WbioSrvc`). | `modules/profile_manager.py:107-115`, `:155-163` | K5-tel együtt tartósan kimaradnak a biztonsági frissítések; a Windows Hello ujjlenyomat/arc nem működik. |
| K8 | **Az összes `svchost.exe` `below_normal` prioritásra kerül**, és ezt semmi nem állítja vissza. A „Folyamat prioritás” gomb hívja. | `modules/ram_cleaner.py:87-94`, `gui/app.py:649`, `:1151-1155` | Hang- és hálózati akadás (az Audiosrv és a hálózati szolgáltatások svchostban futnak). |
| K9 | **Nincs rendszer-visszaállítási pont és nincs `.reg` export** az első módosítás előtt. Az egyetlen védőháló a fenti, hibás JSON. | teljes kódbázis | Egy hiba után nincs független mentés. |
| K11 | **A Nagle-tweak sosem állt vissza** (a 4a során találva). A mentés kulcsa `"{GUID}_TCPNoDelay"`, és a visszaállítás ezt a teljes kulcsot használta registry-értéknévként. | `modules/registry_tweaks.py:461`, `:672-692` | A `TCPNoDelay` és a `TcpAckFrequency` a „sikeres” visszaállítás után is beállítva maradt. |
| K10 | **A mentések nem atomikusan íródnak** (`open(..., "w")` közvetlenül a célfájlra). | `utils/state_manager.py:76`, `modules/registry_tweaks.py:101`, `modules/profile_manager.py:215` | Összeomlás vagy áramszünet írás közben sérült mentést hagy, a Restore ezután semmit nem tud. |

### 1.3 Magas súlyosságú hibák és biztonsági kockázatok

| # | Hiba | Hely |
|---|---|---|
| M1 | **Tkinter szálbiztonság:** háttérszálból közvetlen widget-hívás (`self.boost_log.log(...)`, `self.ram_log.log(...)`). Véletlenszerű `RuntimeError: main thread is not in main loop` vagy fagyás. A többi helyen `self.after(0, ...)` megy háttérszálból, ami szintén nem garantáltan szálbiztos. | `gui/app.py:1133`, `:1141`, `:1153` |
| M2 | **A monitorozás terheli a gépet játék közben.** Az iGPU-monitor 2 mp-enként új PowerShellt indít 5 `Get-Counter` hívással; egyetlen counter ezen a gépen 1,7 s. A hőmérséklethez 2 mp-enként `wmic` indul, ami a gépen nincs (Win11 24H2 óta alapból nincs telepítve), ezért a hőmérséklet mindig N/A. | `modules/igpu_monitor.py:188-235`, `modules/monitor.py:44-61` |
| M3 | **Bizalmi határ: emelt jogú folyamat felhasználó által írható helyről olvas.** Az `custom_profiles.json` az exe mellett van, a `stop_services` listát semmi nem validálja, így bármely szolgáltatásnév letiltható (pl. `mpssvc` tűzfal, `EventLog`). A `main.py` az írható app-mappát a `sys.path` elejére teszi. Egy írható mappába (pl. Letöltések) kicsomagolt onedir build DLL-eltérítésre ad lehetőséget emelt jogon. | `main.py:68-69`, `gui/app.py:22`, `modules/profile_manager.py:193-207` |
| M4 | **A registry-fül állapotjelzése sosem lesz zöld:** a GUI `GPU Priority = 18`-at vár, a modul `8`-at ír; a leírás „8→18”-at ígér. | `gui/app.py:1260`, `:1371`, `:1447`, `modules/registry_tweaks.py:162` |
| M5 | **A Boost-állapot nem perzisztens:** újraindítás után a GUI „INAKTÍV”-ot mutat, miközben a szolgáltatások le vannak tiltva. | `gui/app.py:158`, `:1105-1111` |
| M6 | **A Restore nem az eredeti energiasémát állítja vissza,** hanem fixen a Balanced-et. Egyéni vagy Ultimate séma elvész. | `modules/hw_optimizer.py:241` |
| M7 | **A Restore minden nem-letiltott szolgáltatást elindít,** akkor is, ha eredetileg nem futott. | `modules/hw_optimizer.py:83-84` |
| M8 | **`Win32PrioritySeparation` a `ControlSet001` alá íródik,** nem a `CurrentControlSet` alá; nem garantált, hogy ez az aktív. | `modules/registry_tweaks.py:523` |
| M10 | **Szálak közötti versenyhelyzet a folyamatlistán** (a 4a során találva). A psutil a `Process` objektumokat globálisan cache-eli, a `process_iter(attrs)` felülírja a közös `proc.info`-t, így egy másik szál bejárása után `KeyError: 'pid'` jön. Élő futásban előjött az iGPU-monitorban. | `modules/igpu_monitor.py:258-269`, `modules/ram_cleaner.py`, `modules/monitor.py:107-109` |
| M9 | **A Nagle-tweak minden IP-vel rendelkező interfészre ír** (VPN-ekre is). A `TCPNoDelay` registry-értéket a mai Windows nem használja (az alkalmazás socket-opcióként állítja); a játékok többsége UDP-t használ. | `modules/registry_tweaks.py:432-479` |

**Ami rendben van:** minden `subprocess` hívás listás argumentummal megy, `shell=True` nélkül, a PowerShell-szkriptek konstans stringek. Shell-injekciós rést nem találtam.

### 1.4 Placebo és félrevezető állítások

| Funkció | Valóság | Hely |
|---|---|---|
| RAM „tisztítás” (EmptyWorkingSet minden folyamatra, 3 helyen) | A Windows a lapokat azonnal visszatölti, ez lapozást és akadást okoz, beleértve magát a játékot. A kiírt „X+ MB felszabadítva” értéke `sikeres_folyamatok × 2`, kitalált szám. A „GPU shared pool növelve” állítás hamis. | `modules/ram_cleaner.py:33-70`, `modules/hw_optimizer.py:114-129`, `modules/igpu_monitor.py:376-391` |
| MMCSS `GPU Priority` | Microsoft-dokumentáció: a Windows nem használja. | `modules/registry_tweaks.py:162` |
| MMCSS `SFIO Priority` | Microsoft-dokumentáció: nem használt érték. | `modules/registry_tweaks.py:165` |
| `SystemResponsiveness = 0` | A dokumentáció szerint a 10 alatti értéket a Windows 20-ra (alapértékre) állítja. | `modules/registry_tweaks.py:210` |
| MMCSS Games task általában | Csak azokra a szálakra hat, amelyek az `AvSetMmThreadCharacteristics("Games")` API-val regisztrálnak; a legtöbb játék nem teszi. | `modules/registry_tweaks.py:152-188` |
| `MouseDataQueueSize = 20` | Mérhető előny nincs; nagy mintavételű egérnél bemenet veszhet el. | `modules/registry_tweaks.py:495-507` |
| `SysMain` letiltása | SSD-n mérhető FPS-hatás nincs. | `modules/profile_manager.py:108` |
| README: „+3-10% FPS”, „-5-15 ms” | Forrás és mérés nélkül. | `README.md` |

### 1.5 Közepes és alacsony súlyosságú problémák

- **Duplikáció:** `is_admin` 3×, a subprocess-wrapper 2×, a PowerShell-wrapper 2×, `POWER_PLANS` 2×, a working-set ürítés 3×, a prioritásállító 2×. A `registry_optimizer.py` egy régebbi, párhuzamos registry-implementáció ütköző értékekkel (GPU Priority 18 vs. 8) és saját mentésfájllal.
- **Halott Monitor fül:** a `_apply_snapshot` egy mindig egyelemű listát ad át a CPU-diagramnak, a hőmérséklet-, RAM- és órajel-diagramot semmi nem frissíti. (`gui/app.py:925-930`)
- **`StatCard.update()` felülírja a tkinter `Misc.update()`-et** más szignatúrával; ha bármi a beépítettet hívja rajta, `TypeError` lesz. (`gui/app.py:110`)
- **Importáláskor futó mellékhatások:** globális példányok, szálindítás (`modules/igpu_monitor.py:454`, `:516`), mappa-létrehozás (`modules/profile_manager.py:48-49`). Ez nehezíti a tesztelést.
- **Törékeny szöveges parse:** `sc`, `powercfg`, `wmic` kimenetét bontja szavakra. A szolgáltatás-állapot olvasható közvetlenül a registryből (`Services\<név>\Start`, `DelayedAutostart`) vagy a `psutil.win_service_get()`-tel.
- **Hardverfelismerés:** a WMI `AdapterRAM` 32 bites, 4 GB fölötti VRAM-ot hibásan mutat (`modules/hardware_detector.py:123`); az E-mag heurisztika i7-12650H-n 10P+0E-t ad 6P+4E helyett (`:227-236`); a `"lo"` szűrő kiszűri a „Local Area Connection” nevű adaptert (`:285`); az Intel Arc dedikált kártya iGPU-nak minősül; a `Get-WmiObject` elavult.
- **`None` folyamatnév:** `proc.info['name'].lower()` try-blokkon kívül vagy csak psutil-kivételre szűrve. (`modules/ram_cleaner.py:107`, `modules/monitor.py:109`)
- **Túl széles jogosultság:** `PROCESS_ALL_ACCESS`, ahol `PROCESS_SET_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION` elég.
- **GUI:** az iGPU-folyamatlistát 2 mp-enként lebontja és újraépíti (villogás); a fejléc „v2.0”, a cím „v2.1”; „Segue UI Black” elírás (`gui/app.py:467`); az iGPU fül dedikált GPU-s gépen is látszik.
- **Csomagolás:** a `pyproject.toml` URL-jei placeholderek, a `main:main` belépési pont nem működik, mert a `main.py` nincs a csomagban; tesztmappa nincs; a log nem rotálódik és az exe mellé íródik.

### 1.6 Kódminőség összegzés

| Szempont | Állapot |
|---|---|
| UI és backend szétválasztása | Részleges. A modulok GUI-függetlenek, de a `gui/app.py` tartalmaz üzleti döntéseket (auto-boost, státuszszabályok), a backend pedig `gui.app_paths`-ból importál. |
| Hibakezelés | Sok néma `except Exception: pass`. A műveleti eredmény szöveges log, nem strukturált adat, ezért a GUI nem tudja megmutatni, mi sikerült. |
| Típusjelölés | A függvényszignatúrák nagyrészt jelöltek, a callback-ek és a dict-visszatérések nem. |
| Tesztek | Nincsenek. |
| Naplózás | Van, de az eredmény-összesítések (`✓ 7/8 sikeres`) emojis szövegek, gépi feldolgozásra alkalmatlanok. |

---

## 2. FÁZIS: Versenytárs-összevetés és funkcióhiányok

### 2.1 Mit csinálnak jól a többiek, és mit veszünk át

| Eszköz | Erőssége | Amit átveszünk |
|---|---|---|
| **Chris Titus WinUtil** | Tweakek futtatása előtt automatikus visszaállítási pont; „Undo Selected Tweaks” tweakenként; minden új tweakhez kötelező a visszavonó lépés. Szolgáltatásokat „Kézi”-re állít, nem tiltja le őket. | Tweakenkénti undo adatmodell, visszaállítási pont, „Kézi” letiltás helyett. |
| **BleachBit** | Deklaratív tisztítódefiníciók (CleanerML), **előnézet** törlés előtt méretekkel, kivétellista. | Szkennelés → előnézet méretekkel → megerősítés → törlés. |
| **AtlasOS** | Mély debloat playbookkal. Ellenpélda: a teljes visszavonáshoz újratelepítés kell. | Semmi visszafordíthatatlant nem csinálunk. |
| **Razer Cortex** | Játékindítás felismerése és automatikus mód; a hatás nagy része (RAM-ürítés, folyamatok leállítása) placebo. | Csak a munkamenet-logikát: játék indul → profil be, játék kilép → minden vissza. |
| **Process Lasso** | Tartós, folyamatonkénti prioritás- és affinitásszabályok. | Szabály a játék folyamatára, a háttérfolyamatokra csak a felhasználó által kijelöltekre. |
| **Stacer (Linux)** | Átlátható információs architektúra: Dashboard, Startup, Services, Cleaner, Resources. | Ezt az oldalfelosztást. |
| **LibreHardwareMonitor** | Valódi CPU-hőmérséklet, de ehhez kernel-driver kell. A régi WinRing0 drivert a Defender 2025 óta sebezhető driverként jelzi; az LHM PawnIO-ra váltott. | Kernel-drivert nem csomagolunk. Ha a felhasználónál fut LHM, olvassuk a WMI-névterét. |

### 2.2 Amit kivezetünk

A RAM-„tisztítás”, az MMCSS `GPU Priority`, `SFIO Priority`, `SystemResponsiveness=0`, a `MouseDataQueueSize`, a `SysMain`, `wuauserv` és `WbioSrvc` letiltása, valamint a teljes `svchost` prioritáscsökkentés. A `Win32PrioritySeparation` és a Nagle-tweak opcionálisan egy „Kísérleti” csoportba kerülhet, FPS-ígéret nélkül (ez nyitott döntés, lásd 6. pont).

### 2.3 Új funkciók (valódi, ellenőrizhető hatással)

**P1: biztonsági alap (minden más ezekre épül)**

1. **Változásnapló (journal):** minden módosítás egy `Change` rekord (`típus`, `cél`, `előtte`, `utána`, `időpont`). Az „előtte” értéket csak akkor rögzíti, ha arra a célra még nincs nyitott bejegyzés (ez javítja K1-et). Atomikus írás (`tmp` + `os.replace`).
2. **Egykattintásos „Mindent visszaállít”:** fordított sorrendben görgeti vissza a naplót; a sikertelen tételek bent maradnak újrapróbáláshoz (K4).
3. **Rendszer-visszaállítási pont** az első módosítás előtt (`SystemRestore.CreateRestorePoint`). Kezeli, ha a C: meghajtón ki van kapcsolva a rendszervédelem, és a 24 órás alapértelmezett gyakorisági limitet.
4. **Indításkori ellenőrzés:** ha az előző munkamenet módosításai visszaállítatlanok, az app rákérdez.

**P1: Játék mód (munkamenet-alapú)**

5. Játékfolyamat felismerése a felhasználó listájából (exe név vagy útvonal). Indításkor:
   - energiaséma: Ultimate Performance (ha nincs, `powercfg -duplicatescheme`), Modern Standby laptopon a Windows 11 energiamód (`PowerSetActiveOverlayScheme`, „Legjobb teljesítmény”), mert ott csak a Balanced séma létezik;
   - a játékfolyamat `HIGH` prioritása (`REALTIME` soha);
   - a felhasználó által kijelölt háttérappok prioritáscsökkentése vagy felfüggesztése, rendszerfolyamatok nélkül;
   - a játék kilépésekor minden automatikusan visszaáll a naplóból.

**P2: tisztítás előnézettel**

6. Kategóriák, mindegyikhez szkennelt méret és előnézet: `%TEMP%` és `C:\Windows\Temp` (24 óránál régebbi fájlok), DirectX shader cache (`%LOCALAPPDATA%\D3DSCache`), NVIDIA (`%LOCALAPPDATA%\NVIDIA\DXCache`, `GLCache`), AMD (`%LOCALAPPDATA%\AMD\DxCache`, `DxcCache`, `VkCache`), Delivery Optimization cache (`Delete-DeliveryOptimizationCache`), összeomlási dumpok, Windows Update komponens-takarítás (`DISM /StartComponentCleanup`, lassú, külön gomb). A zárolt fájlokat kihagyja. A felület kiírja, hogy a shader cache törlése után az első játékindítás akadhat; ez helyfelszabadítás és sérült cache javítása, nem FPS-növelés. A Lomtár ürítése csak külön, kifejezett megerősítéssel.

**P2: indítópult és szolgáltatások**

7. **Indítópult:** `HKCU/HKLM ...\Run`, Startup mappa. Ki/be kapcsolás a `StartupApproved` kulcson keresztül, ugyanúgy, ahogy a Feladatkezelő csinálja, így visszafordítható.
8. **Szolgáltatások:** szerkesztett engedélylista kockázati szinttel (pl. `DiagTrack`, `dmwappushservice`, `MapsBroker`, `RetailDemo`, `XblGameSave` ha nincs Xbox-használat). Letiltás helyett „Kézi”. Telemetria: az `AllowTelemetry=0` csak Enterprise/Education kiadáson érvényes, Pro kiadáson a minimum 1; a felület ezt kiírja.

**P2: valós idejű monitor alacsony költséggel**

9. CPU, RAM, lemez, hálózat `psutil`-lal; GPU-kihasználtság és VRAM PDH-val **folyamaton belül** (`ctypes` + `PdhAddEnglishCounterW`), PowerShell-indítás nélkül, egy mintavevő szálon, 1 s-onként.
10. Hőmérséklet driver nélkül, amennyire lehet: NVIDIA GPU `nvidia-ml-py` (NVML) opcionális függőséggel; ACPI hőzóna a `\Thermal Zone Information(*)\Temperature` counterrel, „rendszer/hőzóna” címkével, nem „CPU mag” címkével; ha fut LibreHardwareMonitor, annak WMI-adatai.

**P3: hálózat és állapotjelzés**

11. DNS-választó (DHCP / Cloudflare / Quad9 / Google) naplózott visszaállítással, DNS-gyorsítótár ürítése, ping/jitter mérés egy választott célra.
12. Csak állapotjelzés és útmutató (automatikus kapcsolás nélkül): HAGS (a DLSS Frame Generation igényli), VBS/Memóriaintegritás (egyes játékokban mérhető hatás, de biztonsági kompromisszum), Game Mode, „Ablakos játékok optimalizálása” (`DirectXUserGlobalSettings`), hibrid GPU-s laptopon alkalmazásonkénti GPU-preferencia (`UserGpuPreferences`).

---

## 3. FÁZIS: UI/UX és szerkezeti újratervezés

### 3.1 A jelenlegi felület értékelése

| Probléma | Részlet |
|---|---|
| Függőleges hely | A fejléc (60 px) és a fix monitorsáv (112 px) a 760 px-es ablakból 172 px-et elvesz minden fülön. |
| Navigáció | 7 felső fül emoji-ikonokkal; az iGPU fül dedikált GPU-n is látszik; a felelősségek keverednek (RAM-gomb a Boost fülön, prioritásgomb a RAM fülön). |
| Visszajelzés | Az elsődleges visszajelzés egy konzolszerű napló. Nincs folyamatjelző, nincs toast, nincs összesítés arról, mi sikerült és mi nem. |
| Biztonság a UI-ban | Rendszermódosítás előtt nincs megerősítő ablak és nincs „mi fog változni” előnézet. |
| Kontraszt | A másodlagos szöveg (`#4A5568`) a kártyán (`#1A1F2E`) kb. **2,2:1**, a WCAG 4,5:1 alatt; 9 px-es feliratok. |
| Témakezelés | Nyers hex értékek widgetenként, nincs tokenrendszer; az accent színe profilonként változik. |
| Ikonok | Emoji, betűtípus-függő megjelenéssel. |

### 3.2 Új információs architektúra (bal oldali sáv)

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│ GameBooster  │  Áttekintés                              [Admin ✓]       │
│              │                                                          │
│ ▸ Áttekintés │  ┌ CPU ──────┐ ┌ RAM ──────┐ ┌ GPU ──────┐ ┌ Lemez ────┐ │
│   Játék mód  │  │ 23 %      │ │ 61 %      │ │ 12 %      │ │ 41 %      │ │
│   Tisztítás  │  │ ▁▂▃▂▁▂▃▅  │ │ 9,8/16 GB │ │ 1,2 GB    │ │ C: 212 GB │ │
│   Indítópult │  └───────────┘ └───────────┘ └───────────┘ └───────────┘ │
│   Szolgált.  │  ┌ Aktív módosítások ───────────┐ ┌ Gyors műveletek ─────┐ │
│   Tweakek    │  │ 4 változás, 2 modulban       │ │ [Játék mód indítása] │ │
│   Hálózat    │  │ Utolsó: 14:32 Játék mód      │ │ [Tisztítás: szken]   │ │
│   Monitor    │  │ [Részletek] [Mindent vissza] │ │                      │ │
│ ──────────── │  └──────────────────────────────┘ └──────────────────────┘ │
│   Előzmények │                                                          │
│   Beállítás  │                          ┌ Toast: Tisztítás kész, 1,4 GB ┐│
└──────────────┴──────────────────────────┴───────────────────────────────┘
```

- **Áttekintés:** státuszkártyák, aktív módosítások száma „Mindent visszaállít” gombbal, gyors műveletek.
- **Játék mód:** játéklista, mit fog változtatni (előnézet), munkamenet állapota.
- **Tisztítás:** szkennelés → kategóriák méretekkel, jelölőnégyzetekkel → megerősítés → folyamatjelző.
- **Indítópult / Szolgáltatások:** táblázat (`ttk.Treeview` sötét stílussal), kapcsoló, kockázati jelvény.
- **Tweakek:** csoportosított kapcsolók, mindegyiken „Hatás: mérhető / helyzetfüggő / kísérleti” és „Újraindítás kell” jelvény.
- **Előzmények:** a változásnapló listája tételenkénti visszavonással, a visszaállítási pontok listája.

### 3.3 Vizuális rendszer (sötét elsődleges téma)

| Token | Érték | Megjegyzés |
|---|---|---|
| `bg` | `#0F1115` | ablak háttér |
| `surface` / `surface-2` | `#171A21` / `#1F232C` | kártyák, beágyazott panelek |
| `border` | `#2A2F3A` | elválasztók |
| `text` / `text-muted` | `#E6E9EF` / `#9AA3B2` | a muted kb. 6,8:1 a `surface`-en |
| `accent` | egyetlen márkaszín (pl. `#3DDC97`) | a profilonkénti színek megszűnnek |
| `success` / `warning` / `danger` / `info` | szemantikus színek | mindig ikonnal vagy szöveggel együtt, nem csak színnel |

- **Betűk:** Segoe UI Variable (Windows 11 beépített), törzsszöveg 13-14 px, minimum 12 px; mérőszámokhoz Cascadia Mono / Consolas (táblázatos számjegyek, nem ugrál a szélesség).
- **Ikonok:** a Windows 11 beépített **Segoe Fluent Icons** betűtípusa, emoji helyett, új függőség nélkül.
- **Térköz:** 8 px-es rács (8/16/24/32).
- **Állapotok:** minden hosszú műveletnél a gomb letiltva + `CTkProgressBar` (indeterminált, ha nincs becsülhető hossz); toast 4 s után eltűnik, nem veszi el a fókuszt; rendszermódosítás előtt megerősítő ablak a változások listájával; visszavonás toastból.
- **Animáció:** csak állapotváltáshoz (folyamatjelző, toast be/ki). Tk-ban nincs GPU-gyorsított animáció, ezért díszítő mozgás nem lesz.

### 3.4 Válaszkészség (szálmodell)

- Egy `TaskRunner`: `concurrent.futures.ThreadPoolExecutor` a munkához, és egy `queue.Queue`, amelyet a főszál `after(50)` ciklusa ürít. **Widgethez csak a főszál nyúl** (M1 javítása).
- A műveletek strukturált eredményt adnak vissza (`ok`, `failed`, `skipped` tételek), a UI ebből rajzol összesítőt; a szöveges napló másodlagos részletnézet.
- Hosszú szkennelésnél (tisztítás) megszakítási token.
- Egyetlen mintavevő szál a monitorhoz, PowerShell nélkül (M2 javítása). Widgetet nem épít újra, csak a meglévőket frissíti.

### 3.5 Javasolt projektszerkezet

```
pc-optimizer/
├── main.py                    # csak indítás: admin-ellenőrzés, logging, app
├── gamebooster/
│   ├── core/
│   │   ├── journal.py         # Change rekord, atomikus JSON, revert_all()
│   │   ├── winapi.py          # is_admin, run(), registry r/w, service API (egy helyen)
│   │   ├── restore_point.py
│   │   └── paths.py           # %LOCALAPPDATA%\GameBooster (migráció az exe mellől)
│   ├── optimizers/            # mind: plan() -> list[Change], apply(plan), status()
│   │   ├── power.py
│   │   ├── services.py
│   │   ├── registry_tweaks.py
│   │   ├── game_mode.py
│   │   ├── cleaner.py
│   │   ├── startup.py
│   │   └── network.py
│   ├── monitoring/
│   │   ├── sampler.py         # psutil + PDH, egy szál
│   │   └── hardware.py
│   ├── profiles.py
│   └── ui/
│       ├── app.py             # shell: oldalsáv, oldalváltás, TaskRunner
│       ├── theme.py           # tokenek
│       ├── widgets/           # StatCard, Sparkline, Toast, ConfirmDialog
│       └── pages/             # dashboard.py, game_mode.py, cleaner.py, ...
└── tests/                     # pytest; winreg és szolgáltatás-API hamisítva
```

Miért nem `src/` elrendezés: egyetlen alkalmazásról van szó, nem könyvtárról; a sima csomagmappa PyInstallerrel és `python main.py`-jal is beállítás nélkül működik. A `core` nem importálhat a `ui`-ból; az `optimizers` modulok GUI nélkül, tesztből is hívhatók. A globális példányok és az importáláskori szálindítás megszűnnek: az `ui/app.py` hozza létre és indítja őket.

Az írható adatok (napló, profilok, log rotációval) a `%LOCALAPPDATA%\GameBooster` mappába kerülnek; az emelt jogú folyamat a felhasználó által írható exe-mappából nem tölt be konfigurációt validálás nélkül (M3). Az egyéni profil szolgáltatáslistája csak az engedélylista elemeit fogadja el.

---

## 4. FÁZIS: végrehajtási terv (jóváhagyás után)

Munka egy külön ágon (`refactor/v3`), lépésenként helyi commitokkal; push csak a jóváhagyásoddal. Rendszert módosító útvonalat ezen a gépen nem futtatok; az apply/revert ellenőrzése egységtesztekkel (hamisított registry és szolgáltatás-API) és a végén Windows Sandboxban vagy VM-ben történik.

| Lépés | Tartalom | Méret | Ellenőrzés |
|---|---|---|---|
| **4a Hotfix** a mostani kódon | K1 (meglévő mentést nem ír felül), K2 (a ténylegesen módosított listát menti), K3 (`Start` + `DelayedAutostart` olvasása a registryből), K4 (hiba esetén a mentés marad), K5/K6 (auto-boost ki, kilépéskor kérdés), K7/K8 (`wuauserv`, `WbioSrvc`, `svchost` ki), K10 (atomikus írás), M1 (szálbiztos naplózás), M4 (GPU Priority jelzés). Kb. 100-150 sor. | Kicsi | pytest a mentés/visszaállítás logikára; kézi futtatás csak olvasó módban |
| **4b Core** | `journal.py`, `winapi.py`, `paths.py` (+ migráció), `restore_point.py`; tesztek | Közepes | pytest: napló-körút, ismételt apply nem írja felül az eredetit, atomikus írás |
| **4c Modulok átköltöztetése** | power, services, registry (placebo-tételek nélkül), monitor (PDH folyamaton belül); a holt modulok törlése | Közepes | pytest + a régi és új plan() kimenet összevetése |
| **4d Új funkciók** | Játék mód munkamenettel, tisztítás előnézettel, indítópult, szolgáltatás-engedélylista, DNS/ping | Nagy | pytest; tisztítás csak ideiglenes tesztmappán; Sandbox-próba |
| **4e UI-keret** | oldalsáv, tokenek, TaskRunner, oldalak, toast, megerősítő ablak, Előzmények oldal | Nagy | app indítása, minden oldal betölt, szálhiba nincs a logban; képernyőképek |
| **4f Takarítás és build** | `osszes_kod.txt`, `main.spec` törlése; `pyproject.toml` javítása; spec frissítése; README őszinte állításokkal; `ruff` + pytest egy GitHub Actions `windows-latest` jobban | Kicsi | `build.bat` sikeres, az exe elindul |

A 4a-t érdemes külön kiadásként is közzétenni, mert a mostani v2.1 a felhasználók gépén is K1-K8 hibákkal fut.

---

## 5. Kockázatok

| Kockázat | Valószínűség | Kezelés |
|---|---|---|
| A tesztelés valódi rendszert módosít | Közepes | Egységtesztek hamisított API-val; integrációs próba Windows Sandboxban/VM-ben, sosem a fejlesztői gépen. |
| A visszaállítási pont létrehozása elmarad (kikapcsolt rendszervédelem, 24 órás limit) | Magas | A UI kiírja, és a napló alapú visszaállítás ettől függetlenül működik. |
| A tisztító felhasználói adatot töröl | Alacsony, súlyos | Csak rögzített, ismert cache-útvonalak; előnézet; korhatár a Temp-fájlokra; Lomtár csak külön megerősítéssel. |
| A Defender gyanúsnak jelöli a PyInstaller exe-t | Közepes | Nincs kernel-driver, nincs `ExecutionPolicy Bypass` PowerShell; kódaláírás opcióként. |
| A meglévő v2.1 felhasználók letiltott szolgáltatásokkal maradtak | Közepes | Az új verzió első indításkor felismeri a régi `original_state.json`-t, és felajánlja a visszaállítást (a K3 javított logikájával). |
| A CustomTkinter korlátai (nincs táblázat, gyenge DPI-kezelés) | Közepes | `ttk.Treeview` sötét stílussal; ha nem elég, a 6.1 döntés újranyitható. |

---

## 6. Nyitott döntések (a jóváhagyáshoz)

1. **UI-keretrendszer.** *Javaslat: CustomTkinter marad*, az új oldalsávos szerkezettel. Alternatíva: PySide6 (jobb táblázatok, diagramok, szálkezelés jelekkel), de ez a teljes UI újraírása és kb. 60-100 MB-tal nagyobb csomag.
2. **Placebo-tweakek.** *Javaslat: törlés.* Alternatíva: egy „Kísérleti” csoport hatásígéret nélkül (`Win32PrioritySeparation`, Nagle).
3. **`osszes_kod.txt`.** *Javaslat: törlés a jelenlegi commitból.* A git-előzmények átírása (force push) a 23 MB-ot a klónból is eltüntetné, de ez visszafordíthatatlan művelet a távoli repón.
4. **Hotfix külön kiadásként.** *Javaslat: igen*, a 4a után v2.1.1 néven, a refaktor előtt.
5. **Nyelv.** *Javaslat: a UI magyar marad*, i18n-réteg nélkül.

---

## Források

- Microsoft: [Multimedia Class Scheduler Service](https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service) (GPU Priority „not yet used”, SystemResponsiveness 10 alatt → 20)
- Chris Titus Tech: [winutil in 2026](https://christitus.com/winutil-in-2026/), [Restore Point - Create](https://winutil.christitus.com/code-reference/tweaks/essential-tweaks/restorepoint/)
- [Windows 11/10 is flagging WinRing0 (Neowin)](https://www.neowin.net/news/windows-1110-is-flagging-winring0-on-your-pc-monitoring-fan-control-apps-heres-why/), [OpenRGB: PawnIO a WinRing0 helyett](https://gitlab.com/CalcProgrammer1/OpenRGB/-/merge_requests/2833)
- Élő ellenőrzés ezen a gépen: `sc qc WSearch` → `AUTO_START (DELAYED)`; `where wmic` → nem található; egy `Get-Counter` GPU-lekérdezés friss PowerShellben 1,7 s.
