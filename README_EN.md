<div align="right">
<strong>English</strong> | <a href="README.md">Polski</a>
</div>

# Joan 6: AppDaemon Dashboard Generator

![Version](https://img.shields.io/badge/version-1.1.5-blue) ![E-Ink](https://img.shields.io/badge/Optimized%20for-E--Ink-black) ![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-41bdf5)

**A professional dashboard generator for Visionect Joan 6 tablets, powered by AppDaemon.**

This add-on provides a graphical user interface (GUI) that allows you to easily design screen layouts for your Joan device and generates optimized YAML code for AppDaemon.

<img width="800" height="200" alt="logo" src="https://github.com/user-attachments/assets/8d6bf413-d84b-4d29-b131-bc60264ca2e8" />

## ✨ Key Features

* **⚡ Live Preview (E-Ink Preview):** See a simulated layout of the 6-inch Joan screen directly in your browser.
* **🎨 E-Ink Optimization:** The generated code enforces high contrast (black text on a white background), removes unnecessary colors, and bolds fonts for maximum readability on e-paper screens.
* **🔄 Importing and Editing:** You can import existing YAML code for dashboards, edit their layouts, and adjust widget properties.
* **➕ Creating New Dashboards:** The add-on makes it easy to start building new screen layouts from scratch, tailored to your needs.
* **🔌 Home Assistant Integration:**
    * Automatically fetches a list of your entities (lights, sensors, blinds, etc.).
    * Intelligently assigns MDI icons based on the entity name (e.g., type `light.living_room` and the icon changes to a light bulb).
* **🌍 Bilingual (PL / EN):** The interface and on-screen statuses (e.g., "ON" vs "OFF") are fully translated.
* **🚀 Multipurpose Widgets:**
    * Switches (Switch/Light)
    * Sensors (Temperature, Battery, etc.)
    * Covers and Gates (Cover)
    * Media Players
    * **Navigation (Dashboard Switcher):** Easily create buttons to navigate between pages.

## 📥 Installation

### Step 1: Add Repository
1. In Home Assistant, go to **Settings** -> **Add-ons** -> **Add-on Store**.
2. Click the menu button (three dots) in the top right corner -> **Repositories**.
3. Add the URL of this repository.

### Step 2: Install the Add-on
1. Find the **Joan 6: AppDaemon Dashboard Generator** add-on in the list.
2. Click **Install**.
3. **Important:** Start the add-on and ensure the option **"Show in Sidebar"** is enabled.

## ⚙️ Configuration

The add-on typically works automatically, fetching the token from the HA system.

If the entity list is empty, you can manually generate a token:
1. Click your profile in HA (bottom left) -> Security -> Scroll down to **Long-lived Access Tokens** -> **Create Token**.
2. Paste the token into the `manual_token` field in the add-on configuration.

## 📖 How to Use?

1. Open the **Add-on Web UI**.
2. Choose a language (PL/EN).
3. **Create or edit dashboards**:
    * Import existing dashboard YAML for editing and adjustments.
    * Or start from scratch to create new dashboards.
4. In the **"Add Widget"** section:
    * Select a type (e.g., *Sensor*).
    * Pick an entity from the list (e.g., `sensor.living_room_temperature`).
    * The icon will be selected automatically (you can change it manually).
    * Click **"+ ADD TO ROW"**.
5. Build the layout row by row. Joan 6 is best displayed using **2 columns per row** (large tiles) or **3 columns per row** (smaller tiles).
6. Click **GENERATE .DASH CODE**.
7. Copy the resulting YAML code.

### Where to Save the File?
Create a new `.dash` file in the AppDaemon configuration folder:

```text
\\YOUR_HA_IP\addon_configs\appdaemon\dashboards\joan_living_room.dash
```
