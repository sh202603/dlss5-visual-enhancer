import QtQuick
import ".."

Item {
    id: control

    property string iconSymbol: ""  // e.g. "x", "R", "S", ">", "II", "O", "[]", "..."
    property string tooltipText: ""
    property bool showTooltip: true
    // Vector chrome icon kind: "" (use iconSymbol text), "min", "max", "restore", "close".
    // Vector icons are font-independent so they stay crisp at any DPI/scale.
    property string iconKind: ""
    property bool enabled: true
    property int buttonSize: 28
    property color activeColor: Theme.textSecondary
    property color hoverColor: Theme.textPrimary

    signal clicked()

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    opacity: enabled ? 1.0 : 0.4
    activeFocusOnTab: enabled
    Keys.onPressed: (event) => { if (enabled && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) { clicked(); event.accepted = true } }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: mouseArea.pressed ? Theme.bgPressed : (mouseArea.containsMouse ? Theme.bgHover : "transparent")
        border.color: control.activeFocus ? Theme.accent : (mouseArea.containsMouse ? Theme.borderSubtle : "transparent")
        border.width: 1

        Behavior on color {
            ColorAnimation { duration: Theme.animFast }
        }
    }

    Text {
        visible: control.iconKind === ""
        anchors.centerIn: parent
        text: control.iconSymbol
        font.family: Theme.fontFamily
        font.pixelSize: 13
        color: mouseArea.containsMouse ? control.hoverColor : control.activeColor
    }

    // Vector window-chrome icons (no font glyphs, DPI-independent).
    Item {
        visible: control.iconKind !== ""
        anchors.centerIn: parent
        width: 12
        height: 12
        property color iconColor: mouseArea.containsMouse ? control.hoverColor : control.activeColor

        // Minimize: centered horizontal bar.
        Rectangle {
            visible: control.iconKind === "min"
            anchors.centerIn: parent
            width: 10
            height: 1.6
            color: parent.iconColor
        }

        // Maximize: single outline square.
        Rectangle {
            visible: control.iconKind === "max"
            anchors.centerIn: parent
            width: 10
            height: 10
            color: "transparent"
            border.color: parent.iconColor
            border.width: 1.5
        }

        // Restore: two overlapping squares (back offset up-right).
        Item {
            visible: control.iconKind === "restore"
            anchors.centerIn: parent
            width: 12
            height: 12
            property color rc: parent.iconColor
            Rectangle {
                x: 3; y: 0; width: 8; height: 8
                color: "transparent"
                border.color: parent.rc
                border.width: 1.4
            }
            Rectangle {
                x: 1; y: 3; width: 8; height: 8
                color: bg.color
                border.color: parent.rc
                border.width: 1.4
            }
        }

        // Close: X from two rotated bars.
        Item {
            visible: control.iconKind === "close"
            anchors.centerIn: parent
            width: 12
            height: 12
            property color xc: parent.iconColor
            Rectangle {
                anchors.centerIn: parent
                width: 12.5
                height: 1.6
                rotation: 45
                color: parent.xc
            }
            Rectangle {
                anchors.centerIn: parent
                width: 12.5
                height: 1.6
                rotation: -45
                color: parent.xc
            }
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: control.enabled
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (control.enabled) control.clicked()
        }
    }

    // Tooltip (opt-out via showTooltip; window-chrome buttons disable it
    // because they sit at y=0 and the popup would clip outside the window).
    Rectangle {
        id: tip
        visible: control.showTooltip && mouseArea.containsMouse && control.tooltipText !== ""
        anchors.bottom: parent.top
        anchors.bottomMargin: 6
        anchors.horizontalCenter: parent.horizontalCenter
        width: tipText.implicitWidth + 12
        height: tipText.implicitHeight + 6
        radius: Theme.radiusSmall
        color: "#0F1216"
        border.color: Theme.borderActive
        border.width: 1
        z: 999

        Text {
            id: tipText
            anchors.centerIn: parent
            text: control.tooltipText
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.textPrimary
        }
    }
}
