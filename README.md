<div align="right">
<strong>Polski</strong> | <a href="README_EN.md">English</a>
</div>

# Joan 6: AppDaemon Dashboard Generator <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=Adam7411&repository=joan_generator&category=integration" target="_blank" rel="noreferrer noopener">
  <img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and go to the repository in HACS." />
</a>

![Version](https://img.shields.io/badge/version-1.1.5-blue) ![E-Ink](https://img.shields.io/badge/Optimized%20for-E--Ink-black) ![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-41bdf5)

**Generator dashboardów dla tabletów Visionect Joan 6, działający w oparciu o AppDaemon.**

Ten dodatek to wizualny kreator (GUI), który pozwala "wyklikać" układ ekranu dla Twojego urządzenia Joan, a następnie generuje gotowy, zoptymalizowany kod YAML dla AppDaemon.

<img width="800" height="200" alt="logo" src="https://github.com/user-attachments/assets/8d6bf413-d84b-4d29-b131-bc60264ca2e8" />

## ✨ Główne Funkcje

* **⚡ Podgląd na żywo (E-Ink Preview):** Widzisz symulację układu 6-calowego ekranu Joan bezpośrednio w przeglądarce.
* **🎨 Optymalizacja E-Ink:** Wygenerowany kod wymusza wysoki kontrast (czarny tekst na białym tle), usuwa zbędne kolory i pogrubia czcionki dla maksymalnej czytelności na ekranach e-papieru.
* **🔄 Wczytywanie i Edycja:** Możesz wczytać istniejący kod YAML dashboardu, edytować jego układ oraz atrybuty widgetów.
* **➕ Tworzenie Nowych Dashboardów:** Dodatek umożliwia łatwe tworzenie od podstaw nowych układów ekranów dostosowanych do Twoich potrzeb.
* **🔌 Integracja z Home Assistant:**
    * Automatycznie pobiera listę Twoich encji (światła, czujniki, rolety, itp.).
    * Inteligentnie dobiera ikony MDI na podstawie nazwy encji (np. wpisz `light.salon`, a ikona zmieni się na żarówkę).
* **🌍 Dwujęzyczny (PL / EN):** Interfejs oraz statusy na ekranie (np. "WŁĄCZONE" vs "ON") są w pełni przetłumaczone.
* **🚀 Obsługa wielu typów widgetów:**
    * Przełączniki (Switch/Light)
    * Sensory (Temperatura, Bateria itp.)
    * Rolety i Bramy (Cover)
    * Odtwarzacze (Media Player)
    * **Nawigacja (Dashboard Switcher):** Łatwe tworzenie przycisków do przełączania stron.

## 📥 Instalacja

### Krok 1: Dodanie repozytorium
1. W Home Assistant przejdź do **Ustawienia** -> **Dodatki** -> **Sklep z dodatkami**.
2. Kliknij przycisk menu (trzy kropki) w prawym górnym rogu -> **Repozytoria**.
3. Dodaj adres URL tego repozytorium.

### Krok 2: Instalacja dodatku
1. Znajdź na liście dodatek **Joan 6: AppDaemon Dashboard Generator**.
2. Kliknij **Zainstaluj**.
3. **Ważne:** Uruchom dodatek i upewnij się, że opcja **"Pokaż na pasku bocznym"** jest włączona.

## ⚙️ Konfiguracja

Dodatek zazwyczaj działa automatycznie, pobierając token z systemu HA.

Jeśli jednak lista encji jest pusta, możesz ręcznie wygenerować token:
1. Kliknij swój profil w HA (lewy dolny róg) -> Bezpieczeństwo -> Przewiń na sam dół a tam -> **Długotrwałe tokeny dostępu** -> **Stwórz token**
2. W konfiguracji dodatku wklej token w pole `manual_token`.

## 📖 Jak używać?

1. Otwórz **Interfejs Użytkownika (Web UI)** dodatku.
2. Wybierz język (PL/EN).
3. **Twórz lub edytuj dashboardy**:
    * Możesz wczytać istniejący kod dashboardu YAML, aby go edytować i dopasowywać.
    * Możesz także rozpocząć od nowego dashboardu.
4. W sekcji **"Dodaj Widget"**:
    * Wybierz typ (np. *Sensor*).
    * Wybierz encję z listy (np. `sensor.temperatura_salon`).
    * Ikona zostanie dobrana automatycznie (możesz ją zmienić).
    * Kliknij **"+ DODAJ DO WIERSZA"**.
5. Buduj układ wiersz po wierszu. Joan 6 najlepiej wygląda w układzie **2 kolumny na wiersz** (duże kafelki) lub **3 kolumny** (mniejsze).
6. Kliknij **GENERUJ KOD .DASH**.
7. Skopiuj wynikowy kod YAML.

### Gdzie zapisać plik?
Utwórz nowy plik z rozszerzeniem `.dash` w folderze konfiguracyjnym AppDaemon:

```text
\\TWOJE_IP_HA\addon_configs\appdaemon\dashboards\joan_salon.dash
```
<img width="1341" height="1276" alt="image" src="https://github.com/user-attachments/assets/e02011a6-7b87-4193-83b0-fa9399ce7a28" />

