## PanelsDCC Language and Product Structure Guide

This guide summarises the agreed principles for how **PanelsDCC** should be described, structured, and communicated across the website, documentation, and marketing materials. Its goal is to keep the system **clear to hobbyists**, **consistent in terminology**, and **aligned with the DCC architecture concept**.

---

# 1. Core Product Concept

PanelsDCC is built around a simple three-stage model that mirrors how a railway is set up and operated:

**Design → Control → Connect**

This structure should underpin all explanations of the system.

| Component | Name        | Meaning                               |
| --------- | ----------- | ------------------------------------- |
| D         | **Design**  | Configure panels, trains, accessories |
| C         | **Control** | Operate the railway                   |
| C         | **Connect** | Interface with the DCC controller     |

These three words form both:

* the **technical architecture**
* the **user mental model**

This alignment is intentional and should be preserved.

---

# 2. Component Definitions

### PanelsDCC Design

The **cloud-based configuration environment**.

Purpose:

* Configure trains
* Set up functions including custom icons and ordering
* Configure accessories
* Configure control panels
* Set up routes and accessory combinations
* Set up sensors (future)
* Define automation and behaviour (future)

Important clarification:

PanelsDCC **Design is not a track layout design tool**.
It is used to **design the control panels and system configuration** that operate the railway.

Runs:

* in the cloud
* in a web browser
* no installation required

---

### PanelsDCC Control

The **local user interface used to run the railway**.

Purpose:

* Drive trains
* Operate points and signals
* Run routes and accessory combinations
* Provide a visual control panel
* Monitor sensors (future)
* Run routes and automation (future)


Runs:

* on a Raspberry Pi
* accessible from phones, tablets, and computers via a browser
* continues to work without internet once installed and synced with PanelsDCC Design

---

### PanelsDCC Connect

The **hardware interface layer**.

Purpose:

* Connect PanelsDCC to DCC hardware
* Translate commands to the command station

Runs:

* on the Raspberry Pi
* minimual set up to ensure controllers are connected

Users should **rarely need to think about this component**.

---

# 3. Avoid Technical Terminology

Certain language should **never appear in user-facing material**.

Avoid:

* daemon
* middleware
* service layer
* architecture components
* DCC-IO-daemon

Instead use:

* **Design**
* **Control**
* **Connect**

These are the only user-facing component names.

---

# 4. Website Structure

The website should be organised around **user goals**, not internal architecture.

Recommended sections:

### Home

Explain the concept:

* visual control panels
* Raspberry Pi operation
* DCC compatibility

Include the **Design → Control → Connect** explanation.

---

### How It Works

Introduce the three components:

* PanelsDCC Design
* PanelsDCC Control
* PanelsDCC Connect

Include a simple diagram showing:

Cloud → Raspberry Pi → DCC Controller.

---

# 5. Key Messaging and advantages of this architecture

1. All configuration safely stored in the cloud
2. Can configure your layout from anywhere
3. Control devices are commodity, raspberry pis are inexpensive compared to full pc solutions. 
4. Still maintains offline operation for use away from internet

---

# 6. Getting started guide

1. We first install PanelsDCC Connect and test it works with you controller/controllers
2. You then sign up and create your PanelsDCC account, once created you can then download PanelsDCC Control, create your first train and accessory in PanelsDCC Design, finally sync to PanelsDCC Control and you are now ready to scale to your entire layout. 
3. So there is some setup to do, but don't worry, we'll take you through the entire process.

---