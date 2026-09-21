import QtQuick
import ".."

Item {
    id: control

    property string text: ""
    property string iconName: ""
    property int iconSize: Math.min(16, Math.max(12, buttonHeight - 10))
    property string variant: "secondary" // "primary", "secondary", "danger", "ghost"
    // NOTE: uses built-in Item.enabled (do NOT redeclare it here).
    property int buttonHeight: Theme.controlHeight
    property int customRadius: Theme.radiusMedium
    property color customColor: "transparent"

    signal clicked()

    implicitWidth: Math.max(80, label.implicitWidth + (iconName !== "" ? iconSize + 6 : 0) + 24)
    implicitHeight: buttonHeight
    // Default size so the pill always renders, even in plain Row/Column
    // positioners (explicit width:/height: usages override these).
    width: implicitWidth
    height: implicitHeight
    // Disabled primary stays full-strength at the same #06996B so the
    // main action is pixel-identical enabled vs disabled (only
    // clickability differs); other variants dim.
    opacity: enabled ? 1.0 : (control.variant === "primary" ? 1.0 : 0.45)
    activeFocusOnTab: enabled
    Accessible.role: Accessible.Button
    Accessible.name: text
    Keys.onPressed: (event) => {
        if (enabled && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) { clicked(); event.accepted = true }
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: control.customRadius
        border.width: 1

        color: {
            // Primary is permanently #06996B in idle, hover AND disabled:
            // same hardcoded value everywhere so mouse navigate or
            // enabled state can never change it. Secondary keeps the
            // neutral dark look; danger keeps red.
            if (!control.enabled) {
                if (control.variant === "primary") return "#06996B"
                if (control.variant === "danger") return Theme.danger
                return Theme.bgInput
            }
            if (mouseArea.pressed) {
                if (control.variant === "primary") return Theme.accentPressed
                if (control.variant === "danger") return Theme.dangerPressed
                return Theme.bgPressed
            }
            if (mouseArea.containsMouse) {
                // Primary hover is exactly #06996B: zero visible change
                // when navigating the mouse over the button.
                if (control.variant === "primary") return "#06996B"
                if (control.variant === "danger") return Theme.dangerHover
                if (control.variant === "ghost") return Theme.bgHover
                return Theme.bgHover
            }
            // NOTE: must use Qt.colorEqual here. A plain
            // `customColor !== "transparent"` is ALWAYS true (color value
            // vs string literal never compare equal), which used to make
            // every idle button transparent.
            if (!Qt.colorEqual(control.customColor, "transparent")) return control.customColor
            // Idle: primary is always solid #06996B (hardcoded so the main
            // action color can never depend on theme resolution).
            if (control.variant === "primary") return "#06996B"
            if (control.variant === "danger") return Theme.danger
            if (control.variant === "ghost") return "transparent"
            return Theme.bgInput
        }

        border.color: {
            if (control.variant === "primary" || control.variant === "danger") return "transparent"
            if (control.activeFocus) return Theme.accent
            if (mouseArea.containsMouse) return Theme.borderActive
            return Theme.borderDefault
        }

        Behavior on color {
            ColorAnimation { duration: Theme.animFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.animFast }
        }
    }

    Row {
        anchors.centerIn: parent
        spacing: control.iconName !== "" && control.text !== "" ? 6 : 0
        AppIcon {
            iconName: control.iconName
            iconSize: control.iconSize
            color: label.color
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            id: label
            width: Math.min(implicitWidth, Math.max(0, control.width - 24 - (control.iconName !== "" ? control.iconSize + 6 : 0)))
            text: control.text
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeLabel
            font.weight: control.variant === "primary" ? Font.DemiBold : Font.Normal
            color: {
                if (control.variant === "primary") return "#FFFFFF"
                if (control.variant === "danger") return "#FFFFFF"
                if (mouseArea.containsMouse) return Theme.textPrimary
                return Theme.textSecondary
            }
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: control.enabled
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (control.enabled) {
                control.clicked()
            }
        }
    }
}
