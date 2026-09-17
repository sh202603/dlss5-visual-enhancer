import QtQuick
import ".."

Item {
    id: control

    property string text: ""
    property string variant: "neutral" // "neutral", "success", "warning", "danger", "accent"

    implicitWidth: label.implicitWidth + 12
    implicitHeight: 20

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSmall

        color: {
            if (control.variant === "success") return Theme.successBg
            if (control.variant === "warning") return Theme.warningBg
            if (control.variant === "danger") return Theme.dangerBg
            if (control.variant === "accent") return Theme.accentMuted
            return Theme.bgInput
        }

        border.color: {
            if (control.variant === "success") return Theme.success
            if (control.variant === "warning") return Theme.warning
            if (control.variant === "danger") return Theme.danger
            if (control.variant === "accent") return Theme.accent
            return Theme.borderSubtle
        }
        border.width: 1

        Text {
            id: label
            anchors.centerIn: parent
            text: control.text
            font.family: Theme.monoFontFamily
            font.pixelSize: 10
            font.weight: Font.DemiBold
            color: {
                if (control.variant === "success") return Theme.success
                if (control.variant === "warning") return Theme.warning
                if (control.variant === "danger") return Theme.danger
                if (control.variant === "accent") return Theme.accent
                return Theme.textSecondary
            }
        }
    }
}
