import QtQuick
import ".."

Item {
    id: control

    property string label: ""
    property bool checked: false
    property bool enabled: true

    signal toggled(bool isChecked)

    implicitWidth: Math.max(100, labelText.implicitWidth + 28)
    implicitHeight: 24
    opacity: enabled ? 1.0 : 0.45
    activeFocusOnTab: enabled
    Keys.onPressed: (event) => { if (enabled && (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) { toggled(!checked); event.accepted = true } }

    Row {
        anchors.fill: parent
        spacing: 8

        Rectangle {
            id: box
            width: 18
            height: 18
            radius: Theme.radiusSmall
            anchors.verticalCenter: parent.verticalCenter
            color: control.checked ? Theme.accent : Theme.bgInput
            border.color: control.activeFocus ? Theme.accent : (control.checked ? Theme.accent : (mouseArea.containsMouse ? Theme.borderActive : Theme.borderDefault))
            border.width: 1

            Behavior on color { ColorAnimation { duration: Theme.animFast } }
        }

        Text {
            id: labelText
            anchors.verticalCenter: parent.verticalCenter
            text: control.label
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeLabel
            color: mouseArea.containsMouse ? Theme.textPrimary : Theme.textSecondary
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: control.enabled
        cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (control.enabled) {
                control.toggled(!control.checked)
            }
        }
    }
}
