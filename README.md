# Joan 6: AppDaemon Dashboard Generator

![Version](https://img.shields.io/badge/version-1.1.5-blue) ![E-Ink](https://img.shields.io/badge/Optimized%20for-E--Ink-black) ![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-41bdf5)

**Generator profesjonalnych dashboardów dla tabletów Visionect Joan 6, działający w oparciu o AppDaemon.**

Ten dodatek to wizualny kreator (GUI), który pozwala "wyklikać" układ ekranu dla Twojego urządzenia Joan, a następnie generuje gotowy, zoptymalizowany kod YAML dla AppDaemon.

![Logo](logo.png)

## ✨ Główne Funkcje

*   **⚡ Podgląd na żywo (E-Ink Preview):** Widzisz symulację układu 6-calowego ekranu Joan bezpośrednio w przeglądarce.
*   **🎨 Optymalizacja E-Ink:** Wygenerowany kod wymusza wysoki kontrast (czarny tekst na białym tle), usuwa zbędne kolory i pogrubia czcionki dla maksymalnej czytelności na papierze elektronicznym.
*   **🔌 Integracja z Home Assistant:**
    *   Automatycznie pobiera listę Twoich encji (światła, czujniki, rolety, itp.).
    *   Inteligentnie dobiera ikony MDI na podstawie nazwy encji (np. wpisz `light.salon`, a ikona zmieni się na żarówkę).
*   **🌍 Dwujęzyczny (PL / EN):** Interfejs oraz statusy na ekranie (np. "WŁĄCZONE" vs "ON") są w pełni przetłumaczone.
*   **🚀 Obsługa wielu typów widgetów:**
    *   Przełączniki (Switch/Light)
    *   Sensory (Temperatura, Bateria itp.)
    *   Rolety i Bramy (Cover)
    *   Odtwarzacze (Media Player)
    *   **Nawigacja (Dashboard Switcher):** Łatwe tworzenie przycisków do przełączania stron.

## 📥 Instalacja

### Krok 1: Dodanie repozytorium
1. W Home Assistant przejdź do **Ustawienia** -> **Dodatki** -> **Sklep z dodatkami**.
2. Kliknij przycisk menu (trzy kropki) w prawym górnym rogu -> **Repozytoria**.
3. Dodaj adres URL tego repozytorium.

### Krok 2: Instalacja dodatku
1. Znajdź na liście dodatek **Joan 6: AppDaemon Dashboard Generator**.
2. Kliknij **Zainstaluj**.
3. **Ważne:** Uruchom dodatek i upewnij się, że opcja "Pokaż na pasku bocznym" jest włączona.

## ⚙️ Konfiguracja

Dodatek zazwyczaj działa automatycznie, pobierając token z systemu Supervisor.

Jeśli jednak lista encji jest pusta, możesz ręcznie wygenerować token:
1. Kliknij swój profil w HA (lewy dolny róg) -> **Długoterminowe tokeny dostępu** -> **Utwórz token**.
2. W konfiguracji dodatku wklej token w pole `manual_token`.

## 📖 Jak używać?

1. Otwórz **Interfejs Użytkownika (Web UI)** dodatku.
2. Wybierz język (PL/EN).
3. W sekcji **"Dodaj Widget"**:
    *   Wybierz typ (np. *Sensor*).
    *   Wybierz encję z listy (np. `sensor.temperatura_salon`).
    *   Ikona zostanie dobrana automatycznie (możesz ją zmienić).
    *   Kliknij **"+ DODAJ DO WIERSZA"**.
4. Buduj układ wiersz po wierszu. Joan 6 najlepiej wygląda w układzie **2 kolumny na wiersz** (duże kafelki) lub **3 kolumny** (mniejsze).
5. Kliknij **GENERUJ KOD .DASH**.
6. Skopiuj wynikowy kod YAML.

### Gdzie zapisać plik?
Utwórz nowy plik z rozszerzeniem `.dash` w folderze konfiguracyjnym AppDaemon:

```text
\\TWOJE_IP_HA\addon_configs\appdaemon\dashboards\joan_salon.dash
