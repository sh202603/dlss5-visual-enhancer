import QtQuick
import ".."

Item {
    id: control

    property real progress: 0.0 // 0.0 to 1.0
    property string statusText: ""
    property bool indeterminate: false

    implicitWidth: 200
    implicitHeight: 22

    Column {
        anchors.fill: parent
        spacing: 4

        Row {
            width: parent.width
            visible: control.statusText !== "" || control.progress > 0

            Text {
                text: control.statusText
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.textSecondary
                elide: Text.ElideRight
                width: parent.width - pctText.implicitWidth - 8
            }

            Text {
                id: pctText
                text: Math.round(control.progress * 100) + "%"
                font.family: Theme.monoFontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.DemiBold
                color: Theme.accent
                anchors.right: parent.right
            }
        }

        Rectangle {
            width: parent.width
            height: 6
            radius: 3
            color: Theme.bgInput
            border.color: Theme.borderSubtle
            border.width: 1
            clip: true

            Rectangle {
                id: barFill
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                width: Math.max(0, Math.min(parent.width, parent.width * control.progress))
                radius: 3
                color: Theme.accent

                Behavior on width {
                    NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutQuad }
                }
            }
        }
    }
}
