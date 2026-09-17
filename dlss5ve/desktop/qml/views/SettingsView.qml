import QtQuick
import QtQuick.Dialogs
import QtQuick.Controls as QQC2
import ".."
import "../controls"

Rectangle {
    id: root
    property var appBridge: null
    property string presetName: ""
    color: Theme.bgBase

    Flickable {
        anchors.fill: parent; anchors.margins: 28
        contentWidth: width
        contentHeight: settingsCol.implicitHeight + 48
        clip: true; boundsBehavior: Flickable.StopAtBounds

        Column {
            id: settingsCol
            width: Math.min(parent.width, 1120)
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 20

            Column {
                width: parent.width; spacing: 4
                Text { text: "Preferences & System Configuration"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeHeader; font.weight: Font.Bold; color: Theme.textPrimary }
                Text { width: parent.width; text: "Configure hardware assignment, preview behavior, native layout, and portable settings presets."; wrapMode: Text.Wrap; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; color: Theme.textSecondary }
            }

            Flow {
                id: cardFlow
                width: parent.width; spacing: 14
                property real cardWidth: width >= 920 ? (width - spacing) / 2 : width

                AppCard {
                    width: cardFlow.cardWidth; title: "Hardware & GPU Acceleration"; collapsible: false
                    Column {
                        width: parent.width; spacing: 16
                        AppComboBox { width: parent.width; label: "AI Processing GPU (Tensor Cores / NGX)"; model: appBridge ? appBridge.aiGpuChoices : []; currentValue: appBridge ? appBridge.aiGpuUuid : "auto"; onActivated: (v) => { if (appBridge) appBridge.aiGpuUuid = v } }
                        AppComboBox { width: parent.width; label: "Video Processing GPU (NVENC / NVDEC)"; model: appBridge ? appBridge.videoGpuChoices : []; currentValue: appBridge ? appBridge.videoGpuUuid : "auto"; onActivated: (v) => { if (appBridge) appBridge.videoGpuUuid = v } }
                        Text { width: parent.width; wrapMode: Text.Wrap; text: appBridge && appBridge.runtimeState === "Failed" ? appBridge.runtimeError : ("Runtime: " + (appBridge ? appBridge.runtimeState : "Initializing")); font.family: Theme.monoFontFamily; font.pixelSize: Theme.fontSizeSmall; color: appBridge && appBridge.runtimeState === "Failed" ? Theme.danger : Theme.textMuted }
                    }
                }

                AppCard {
                    width: cardFlow.cardWidth; title: "Preview & Rendering Engine"; collapsible: false
                    Column {
                        width: parent.width; spacing: 16
                        AppSegmentedControl { width: parent.width; label: "Preview Encoding Strategy"; model: appBridge ? appBridge.previewEncodingChoices : []; currentValue: appBridge ? appBridge.previewEncoding : "Auto"; onActivated: (v) => { if (appBridge) appBridge.previewEncoding = v } }
                        AppSwitch { width: parent.width; label: "Realtime Preview"; checked: appBridge ? appBridge.autoPreviewEnabled : true; enabled: appBridge ? appBridge.runtimeState === "Ready" : false; onToggled: (v) => { if (appBridge) appBridge.autoPreviewEnabled = v } }
                        AppCheckBox { label: "Full-size high-fidelity image previews"; checked: appBridge ? appBridge.fullSizeImagePreviews : false; onToggled: (c) => { if (appBridge) appBridge.fullSizeImagePreviews = c } }
                        Text { width: parent.width; wrapMode: Text.Wrap; text: "Full-size previews preserve source detail but can use substantially more RAM on large RAW/8K images."; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; color: Theme.textMuted }
                    }
                }

                AppCard {
                    width: cardFlow.cardWidth; title: "Settings Presets"; collapsible: false
                    Column {
                        width: parent.width; spacing: 12
                        AppTextField { width: parent.width; placeholderText: "Preset name (e.g. 4K Master)..."; text: root.presetName; onTextEdited: (t) => root.presetName = t }
                        Row {
                            spacing: 8
                            AppButton {
                                text: "Export Preset..."
                                onClicked: {
                                    if (root.presetName.trim().length === 0) { if (appBridge) appBridge.exportPreset(""); return }
                                    presetSaveDialog.open()
                                }
                            }
                            AppButton { text: "Import..."; onClicked: presetImportDialog.open() }
                        }
                        Text { visible: appBridge && appBridge.presetStatus !== ""; width: parent.width; wrapMode: Text.Wrap; text: appBridge ? appBridge.presetStatus : ""; font.family: Theme.monoFontFamily; font.pixelSize: Theme.fontSizeSmall; color: Theme.accent }
                    }
                }

                AppCard {
                    width: cardFlow.cardWidth; title: "Maintenance & Defaults"; collapsible: false
                    Column {
                        width: parent.width; spacing: 12
                        Text { width: parent.width; wrapMode: Text.Wrap; text: "Factory reset restores all DLSS, upscale, interpolation, GPU, mask, and encoding settings. Window geometry remains a desktop preference."; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; color: Theme.textSecondary }
                        Row {
                            width: parent.width; spacing: 8
                            AppButton { text: "Open Logs"; onClicked: { if (appBridge) appBridge.openFolder(appBridge.currentLogPath) } }
                            AppButton { text: "Reset All Settings to Defaults"; variant: "danger"; onClicked: resetDialog.open() }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: presetImportDialog; title: "Import Preset JSON"; nameFilters: ["JSON Presets (*.json)", "All Files (*.*)"]
        onAccepted: { if (appBridge && selectedFile) appBridge.importPreset(selectedFile.toString()) }
    }
    FileDialog {
        id: presetSaveDialog; title: "Export Preset JSON"; fileMode: FileDialog.SaveFile; nameFilters: ["JSON Presets (*.json)"]
        onAccepted: { if (appBridge && selectedFile) appBridge.exportPresetTo(root.presetName, selectedFile.toString()) }
    }

    QQC2.Dialog {
        id: resetDialog; width: 420; x: Math.max(20, (root.width - width) / 2); y: Math.max(20, (root.height - height) / 2); modal: true
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        leftPadding: 20
        rightPadding: 20
        topPadding: 16
        bottomPadding: 12
        spacing: 8
        // Borderless custom header: the default Dialog title chrome draws
        // its own light separator line under the title.
        header: QQC2.Label {
            text: "Reset all settings?"
            color: Theme.textPrimary; font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle; font.weight: Font.Bold
            leftPadding: 20; rightPadding: 20; topPadding: 16; bottomPadding: 4
        }
        contentItem: Text { width: 360; wrapMode: Text.Wrap; text: "This restores every processing setting and clears the custom mask. This cannot be undone unless you exported a preset."; color: Theme.textPrimary; font.family: Theme.fontFamily }
        // Borderless: the previous danger-colored border read as a light
        // outline around the whole box against the dark surface.
        background: Rectangle { color: Theme.bgSurface; border.width: 0; radius: Theme.radiusLarge }
        onAccepted: { if (appBridge) appBridge.resetToDefaults() }
    }
}
