import QtQuick

pragma Singleton

QtObject {
    id: root

    // =========================================================================
    // Color Palette: Near-black + charcoal with cyan-to-green primary gradient
    // =========================================================================
    readonly property color bgBase: "#0F0F11"        // Near-black main background
    readonly property color bgSurface: "#27272A"     // Dark charcoal cards, sidebar, header, drawers
    readonly property color bgCard: "#27272A"        // Slightly elevated card background
    readonly property color bgInput: "#1B1B1E"       // Text inputs, slider grooves, wells
    readonly property color bgInputHover: "#232326"  // Input hover state
    readonly property color bgHover: "#303034"       // General button / item hover state
    readonly property color bgPressed: "#3A3A3F"     // Button pressed state
    readonly property color bgSelected: "#33363B"    // Selected queue item or tab

    // Borders & Separators
    readonly property color borderSubtle: "#35353A"  // Hairline panel borders
    readonly property color borderDefault: "#45454B" // Input / card borders
    readonly property color borderActive: "#5A5A61"  // Hovered / focused borders
    readonly property color borderAccent: "#0387C2"  // Accent border

    // Primary Action Gradient (cyan-blue -> bright green -> deep green)
    readonly property color primaryGradStart: "#0387C2" // Left side of button
    readonly property color primaryGradMid: "#10B882"   // Green highlight
    readonly property color primaryGradEnd: "#06996B"   // Right side of button

    // Technical Accents (green primary actions)
    readonly property color accent: "#0387C2"        // Primary brand action color
    readonly property color accentHover: "#06996B"   // Primary action hover - always solid green
    readonly property color accentPressed: "#057A54" // Primary action pressed - darker green
    readonly property color primaryDisabled: "#047857"     // Disabled primary - still clearly green
    readonly property color primaryDisabledText: "#C7D2CE" // Text on disabled primary
    readonly property color accentGlow: "#200387C2"  // Subtle glow around active element
    readonly property color accentMuted: "#12333D"   // Background tint for active pill tabs

    // Status Colors
    readonly property color success: "#10B981"       // Complete / Ready / Online
    readonly property color successBg: "#152E25"
    readonly property color warning: "#F59E0B"       // Caution / HDR note
    readonly property color warningBg: "#2F2515"
    readonly property color danger: "#EF4444"        // Stop / Cancel / Error
    readonly property color dangerHover: "#F87171"
    readonly property color dangerPressed: "#DC2626"
    readonly property color dangerBg: "#331818"

    // Typography Colors
    readonly property color textPrimary: "#F1F5F9"   // High contrast off-white
    readonly property color textSecondary: "#A8ADB5" // Subdued labels & hints
    readonly property color textMuted: "#71767E"     // Placeholders & disabled
    readonly property color textAccent: "#079CAC"    // Accent highlighted values

    // =========================================================================
    // Typography Hierarchy
    // =========================================================================
    readonly property string fontFamily: Qt.application.font.family
    readonly property string monoFontFamily: "Consolas"

    readonly property int fontSizeSmall: 11
    readonly property int fontSizeBody: 12
    readonly property int fontSizeLabel: 13
    readonly property int fontSizeSubtitle: 14
    readonly property int fontSizeTitle: 16
    readonly property int fontSizeHeader: 18

    // =========================================================================
    // Geometry & Metrics
    // =========================================================================
    readonly property int radiusSmall: 4
    readonly property int radiusMedium: 6
    readonly property int radiusLarge: 8

    readonly property int controlHeight: 32
    readonly property int controlHeightSmall: 26
    readonly property int controlHeightLarge: 38

    readonly property int spacingSmall: 6
    readonly property int spacingMedium: 10
    readonly property int spacingLarge: 16
    readonly property int spacingHuge: 24

    // =========================================================================
    // Transitions & Animations
    // =========================================================================
    readonly property int animFast: 120
    readonly property int animNormal: 200
    readonly property int animSlow: 300
}
