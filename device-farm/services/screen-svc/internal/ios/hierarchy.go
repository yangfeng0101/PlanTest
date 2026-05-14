package ios

import (
	"encoding/xml"
	"fmt"
	"strconv"
	"strings"
	"time"
)

type uiXMLNode struct {
	XMLName  xml.Name
	Attrs    []xml.Attr  `xml:",any,attr"`
	Children []uiXMLNode `xml:",any"`
}

type UIHierarchyResponse struct {
	DeviceID   string      `json:"device_id"`
	Platform   string      `json:"platform"`
	CapturedAt string      `json:"captured_at"`
	Screen     UIScreen    `json:"screen"`
	Elements   []UIElement `json:"elements"`
	Tree       UITreeNode  `json:"tree"`
}

type UIScreen struct {
	Width  int `json:"width"`
	Height int `json:"height"`
}

type UIElement struct {
	UID                 string               `json:"uid"`
	ParentUID           *string              `json:"parent_uid"`
	Depth               int                  `json:"depth"`
	Index               int                  `json:"index"`
	ClassName           string               `json:"class_name"`
	ResourceID          string               `json:"resource_id"`
	Text                string               `json:"text"`
	ContentDescription  string               `json:"content_desc"`
	Package             string               `json:"package"`
	Bounds              UIBounds             `json:"bounds"`
	Center              UIPoint              `json:"center"`
	Clickable           bool                 `json:"clickable"`
	Enabled             bool                 `json:"enabled"`
	Selected            bool                 `json:"selected"`
	Focused             bool                 `json:"focused"`
	Scrollable          bool                 `json:"scrollable"`
	XPath               string               `json:"xpath"`
	SelectorSuggestions []SelectorSuggestion `json:"selector_suggestions"`
	Attributes          map[string]any       `json:"attributes"`
}

type UITreeNode struct {
	UIElement
	Children []UITreeNode `json:"children"`
}

type UIBounds struct {
	X      int `json:"x"`
	Y      int `json:"y"`
	Width  int `json:"width"`
	Height int `json:"height"`
}

type UIPoint struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type SelectorSuggestion struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}

func ParseIOSHierarchy(xmlText string, deviceID string) (*UIHierarchyResponse, error) {
	xmlText = extractIOSXML(xmlText)
	if xmlText == "" {
		return nil, fmt.Errorf("iOS page source XML is empty")
	}

	var root uiXMLNode
	if err := xml.Unmarshal([]byte(xmlText), &root); err != nil {
		return nil, fmt.Errorf("invalid iOS page source XML: %w", err)
	}

	elements := make([]UIElement, 0)
	uidCounter := 0
	nextUID := func() string {
		uid := fmt.Sprintf("ios-node-%d", uidCounter)
		uidCounter++
		return uid
	}

	var buildNode func(node uiXMLNode, parentUID *string, depth int, absolutePath string) UITreeNode
	buildNode = func(node uiXMLNode, parentUID *string, depth int, absolutePath string) UITreeNode {
		uid := nextUID()
		element := iosElementFromXML(node, uid, parentUID, depth, absolutePath)
		elements = append(elements, element)

		treeNode := UITreeNode{
			UIElement: element,
			Children:  make([]UITreeNode, 0),
		}

		typeCounts := map[string]int{}
		for _, child := range node.Children {
			className := iosClassName(child)
			typeCounts[className]++
			childPath := fmt.Sprintf("%s/%s[%d]", absolutePath, className, typeCounts[className])
			treeNode.Children = append(treeNode.Children, buildNode(child, &uid, depth+1, childPath))
		}
		return treeNode
	}

	rootClass := iosClassName(root)
	tree := UITreeNode{
		UIElement: UIElement{
			UID:       "root",
			ClassName: rootClass,
		},
		Children: make([]UITreeNode, 0),
	}

	if len(root.Children) == 0 {
		tree.Children = append(tree.Children, buildNode(root, nil, 0, fmt.Sprintf("/%s[1]", rootClass)))
	} else {
		typeCounts := map[string]int{}
		for _, child := range root.Children {
			className := iosClassName(child)
			typeCounts[className]++
			absolutePath := fmt.Sprintf("/%s/%s[%d]", rootClass, className, typeCounts[className])
			tree.Children = append(tree.Children, buildNode(child, nil, 0, absolutePath))
		}
	}

	return &UIHierarchyResponse{
		DeviceID:   deviceID,
		Platform:   "ios",
		CapturedAt: time.Now().UTC().Format(time.RFC3339Nano),
		Screen:     iosScreenFromElements(elements),
		Elements:   elements,
		Tree:       tree,
	}, nil
}

func iosElementFromXML(node uiXMLNode, uid string, parentUID *string, depth int, absolutePath string) UIElement {
	attrs := xmlAttrs(node)
	bounds := parseIOSBounds(attrs)
	center := UIPoint{
		X: bounds.X + bounds.Width/2,
		Y: bounds.Y + bounds.Height/2,
	}
	className := iosClassName(node)
	name := attrs["name"]
	label := attrs["label"]
	value := attrs["value"]
	text := firstNonEmpty(label, value, name)
	contentDesc := firstNonEmpty(name, label)
	xpath := iosPrimaryXPath(contentDesc, label, value, className, absolutePath)
	enabled := toBool(attrs["enabled"])
	visible := toBool(attrs["visible"])
	accessible := toBool(attrs["accessible"])

	return UIElement{
		UID:                uid,
		ParentUID:          parentUID,
		Depth:              depth,
		Index:              toInt(attrs["index"]),
		ClassName:          className,
		ResourceID:         "",
		Text:               text,
		ContentDescription: contentDesc,
		Package:            "",
		Bounds:             bounds,
		Center:             center,
		Clickable:          enabled && (visible || accessible),
		Enabled:            enabled,
		Selected:           toBool(attrs["selected"]),
		Focused:            toBool(attrs["focused"]),
		Scrollable:         isIOSScrollable(className),
		XPath:              xpath,
		SelectorSuggestions: iosSelectorSuggestions(
			contentDesc,
			label,
			value,
			className,
			xpath,
		),
		Attributes: map[string]any{
			"absolute_xpath": absolutePath,
			"type":           className,
			"name":           name,
			"label":          label,
			"value":          value,
			"visible":        visible,
			"accessible":     accessible,
		},
	}
}

func extractIOSXML(output string) string {
	output = strings.TrimSpace(output)
	if output == "" {
		return ""
	}
	if idx := strings.Index(output, "<?xml"); idx >= 0 {
		return output[idx:]
	}
	if idx := strings.Index(output, "<"); idx >= 0 {
		return output[idx:]
	}
	return output
}

func xmlAttrs(node uiXMLNode) map[string]string {
	attrs := make(map[string]string, len(node.Attrs))
	for _, attr := range node.Attrs {
		attrs[attr.Name.Local] = attr.Value
	}
	return attrs
}

func iosClassName(node uiXMLNode) string {
	if className := xmlAttrs(node)["type"]; className != "" {
		return className
	}
	if node.XMLName.Local != "" {
		return node.XMLName.Local
	}
	return "XCUIElementTypeOther"
}

func parseIOSBounds(attrs map[string]string) UIBounds {
	x := toRoundedInt(attrs["x"])
	y := toRoundedInt(attrs["y"])
	width := max(0, toRoundedInt(attrs["width"]))
	height := max(0, toRoundedInt(attrs["height"]))
	return UIBounds{X: x, Y: y, Width: width, Height: height}
}

func iosScreenFromElements(elements []UIElement) UIScreen {
	maxX, maxY := 0, 0
	for _, element := range elements {
		bounds := element.Bounds
		if bounds.X+bounds.Width > maxX {
			maxX = bounds.X + bounds.Width
		}
		if bounds.Y+bounds.Height > maxY {
			maxY = bounds.Y + bounds.Height
		}
	}
	for _, preferred := range []string{"XCUIElementTypeApplication", "XCUIElementTypeWindow"} {
		for _, element := range elements {
			bounds := element.Bounds
			if element.ClassName == preferred && bounds.X == 0 && bounds.Y == 0 && bounds.Width > 0 && bounds.Height > 0 {
				return UIScreen{Width: bounds.Width, Height: bounds.Height}
			}
		}
	}
	return UIScreen{Width: maxX, Height: maxY}
}

func iosSelectorSuggestions(accessibilityID, label, value, className, xpath string) []SelectorSuggestion {
	suggestions := make([]SelectorSuggestion, 0, 5)
	if accessibilityID != "" {
		suggestions = append(suggestions,
			SelectorSuggestion{Type: "accessibility_id", Value: accessibilityID},
			SelectorSuggestion{Type: "ios_predicate", Value: "name == " + iosPredicateLiteral(accessibilityID)},
		)
	} else if label != "" {
		suggestions = append(suggestions, SelectorSuggestion{Type: "ios_predicate", Value: "label == " + iosPredicateLiteral(label)})
	} else if value != "" {
		suggestions = append(suggestions, SelectorSuggestion{Type: "ios_predicate", Value: "value == " + iosPredicateLiteral(value)})
	}
	if className != "" {
		if accessibilityID != "" {
			suggestions = append(suggestions, SelectorSuggestion{
				Type:  "ios_class_chain",
				Value: fmt.Sprintf("**/%s[`name == %s`]", className, iosPredicateLiteral(accessibilityID)),
			})
		} else {
			suggestions = append(suggestions, SelectorSuggestion{Type: "ios_class_chain", Value: "**/" + className})
		}
	}
	if label != "" {
		suggestions = append(suggestions, SelectorSuggestion{Type: "text", Value: label})
	}
	if xpath != "" {
		suggestions = append(suggestions, SelectorSuggestion{Type: "xpath", Value: xpath})
	}
	return suggestions
}

func iosPrimaryXPath(accessibilityID, label, value, className, absolutePath string) string {
	if accessibilityID != "" {
		return "//*[@name=" + xpathLiteral(accessibilityID) + "]"
	}
	if label != "" {
		return "//*[@label=" + xpathLiteral(label) + "]"
	}
	if value != "" {
		return "//*[@value=" + xpathLiteral(value) + "]"
	}
	if className != "" {
		return absolutePath
	}
	return absolutePath
}

func xpathLiteral(value string) string {
	if !strings.Contains(value, "'") {
		return "'" + value + "'"
	}
	if !strings.Contains(value, "\"") {
		return `"` + value + `"`
	}
	parts := strings.Split(value, "'")
	quoted := make([]string, 0, len(parts))
	for _, part := range parts {
		quoted = append(quoted, "'"+part+"'")
	}
	return "concat(" + strings.Join(quoted, `, "\"'\"", `) + ")"
}

func iosPredicateLiteral(value string) string {
	if !strings.Contains(value, "'") {
		return "'" + value + "'"
	}
	if !strings.Contains(value, "\"") {
		return `"` + value + `"`
	}
	value = strings.ReplaceAll(value, `\`, `\\`)
	value = strings.ReplaceAll(value, `'`, `\'`)
	return "'" + value + "'"
}

func isIOSScrollable(className string) bool {
	switch className {
	case "XCUIElementTypeScrollView", "XCUIElementTypeTable", "XCUIElementTypeCollectionView":
		return true
	default:
		return false
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func toBool(value string) bool {
	value = strings.TrimSpace(strings.ToLower(value))
	return value == "true" || value == "1"
}

func toInt(value string) int {
	parsed, _ := strconv.Atoi(strings.TrimSpace(value))
	return parsed
}

func toRoundedInt(value string) int {
	parsed, err := strconv.ParseFloat(strings.TrimSpace(value), 64)
	if err != nil {
		return 0
	}
	if parsed < 0 {
		return int(parsed - 0.5)
	}
	return int(parsed + 0.5)
}
