import QtQuick
import ".."
import "../controls"

Rectangle {
    id: root
    property var appBridge: null
    color: Theme.bgBase

    Item {
        anchors.fill: parent; anchors.margins: 28
        Column {
            id: aboutCol
            width: Math.min(parent.width, 1120); anchors.centerIn: parent; spacing: 20
            Column {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 4
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Visual Enhancer"; font.family: Theme.fontFamily; font.pixelSize: 22; font.weight: Font.Bold; color: Theme.textPrimary
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Advanced neural image & video processing"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeLabel; color: Theme.textSecondary
                }
            }

            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                AppButton { text: "GitHub Repository"; onClicked: Qt.openUrlExternally("https://github.com/Merserk/dlss5-visual-enhancer") }
                AppButton { text: "Support on Patreon"; onClicked: Qt.openUrlExternally("https://www.patreon.com/Merserk") }
            }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "© 2026 Merserk. NVIDIA, DLSS, and RTX are trademarks of NVIDIA Corporation."; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; color: Theme.textMuted }
        }
    }
}
