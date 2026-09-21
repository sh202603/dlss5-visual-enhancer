import QtQuick
import ".."

Item {
    id: control

    property string label: ""
    property real from: 0.0
    property real to: 1.0
    property real stepSize: 0.05
    property real value: 0.0
    property real defaultValue: 0.0
    property int precision: 2
    property string unit: ""
    property bool enabled: true

    signal valueModified(real newValue)

    implicitWidth: 260
    implicitHeight: 48
    opacity: enabled ? 1.0 : 0.45
    activeFocusOnTab: enabled

    function keyboardStep(direction) {
        var step = stepSize > 0 ? stepSize : (to - from) / 100
        var next = Math.max(from, Math.min(to, value + direction * step))
        valueModified(next)
    }
    Keys.onPressed: (event) => {
        if (!enabled) return
        if (event.key === Qt.Key_Left || event.key === Qt.Key_Down) { keyboardStep(-1); event.accepted = true }
        else if (event.key === Qt.Key_Right || event.key === Qt.Key_Up) { keyboardStep(1); event.accepted = true }
        else if (event.key === Qt.Key_Home) { valueModified(from); event.accepted = true }
        else if (event.key === Qt.Key_End) { valueModified(to); event.accepted = true }
    }

    // Top row: Label, Reset icon, and Numeric Readout
    Row {
        id: headerRow
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 18

        Text {
            id: labelText
            text: control.label
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeLabel
            color: Theme.textSecondary
            anchors.verticalCenter: parent.verticalCenter
        }

        Item {
            // Spacer
            width: Math.max(8, headerRow.width - labelText.implicitWidth - valueDisplayRow.implicitWidth)
            height: 1
        }

        Row {
            id: valueDisplayRow
            spacing: 6
            anchors.verticalCenter: parent.verticalCenter

            // Reset action
            Rectangle {
                width: 14
                height: 14
                radius: 7
                color: resetArea.containsMouse ? Theme.bgHover : "transparent"
                visible: Math.abs(control.value - control.defaultValue) > 0.001
                anchors.verticalCenter: parent.verticalCenter

                AppIcon {
                    anchors.centerIn: parent
                    iconName: "reset"
                    iconSize: 12
                    color: resetArea.containsMouse ? Theme.accent : Theme.textMuted
                }

                MouseArea {
                    id: resetArea
                    anchors.fill: parent
                    hoverEnabled: control.enabled
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        control.valueModified(control.defaultValue)
                    }
                }
            }

            Text {
                text: {
                    var strVal = control.precision > 0 ? control.value.toFixed(control.precision) : Math.round(control.value).toString()
                    return control.unit !== "" ? (strVal + " " + control.unit) : strVal
                }
                font.family: Theme.monoFontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.DemiBold
                color: Math.abs(control.value - control.defaultValue) > 0.001 ? Theme.accent : Theme.textPrimary
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // Slider track & thumb
    Item {
        id: trackArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 22

        // Background groove
        Rectangle {
            id: groove
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            height: 4
            radius: 2
            color: Theme.bgInput
            border.color: Theme.borderSubtle
            border.width: 1
        }

        // Active highlighted track fill
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: groove.left
            width: Math.max(0, Math.min(groove.width, (thumb.x + thumb.width / 2)))
            height: 4
            radius: 2
            color: Theme.accent
        }

        // Thumb handle
        Rectangle {
            id: thumb
            y: (trackArea.height - height) / 2
            x: {
                var range = control.to - control.from
                if (range <= 0) return 0
                var pct = Math.max(0.0, Math.min(1.0, (control.value - control.from) / range))
                return pct * (trackArea.width - width)
            }
            width: 14
            height: 14
            radius: 7
            color: sliderMouse.containsMouse || sliderMouse.drag.active ? "#FFFFFF" : Theme.textPrimary
            border.color: control.activeFocus || sliderMouse.drag.active ? Theme.accent : Theme.borderActive
            border.width: 2

            Rectangle {
                anchors.centerIn: parent
                width: 4
                height: 4
                radius: 2
                color: Theme.accent
            }

            Behavior on scale {
                NumberAnimation { duration: Theme.animFast }
            }
        }

        MouseArea {
            id: sliderMouse
            anchors.fill: parent
            hoverEnabled: control.enabled
            cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor

            function updateValue(mouseX) {
                var clampedX = Math.max(0, Math.min(trackArea.width - thumb.width, mouseX - thumb.width / 2))
                var pct = clampedX / (trackArea.width - thumb.width)
                var rawVal = control.from + pct * (control.to - control.from)
                if (control.stepSize > 0) {
                    var steps = Math.round((rawVal - control.from) / control.stepSize)
                    rawVal = control.from + steps * control.stepSize
                }
                rawVal = Math.max(control.from, Math.min(control.to, rawVal))
                control.valueModified(rawVal)
            }

            onPressed: (mouse) => {
                if (control.enabled) updateValue(mouse.x)
            }

            onPositionChanged: (mouse) => {
                if (control.enabled && pressed) updateValue(mouse.x)
            }

            onDoubleClicked: {
                if (control.enabled) {
                    control.valueModified(control.defaultValue)
                }
            }
        }
    }
}
