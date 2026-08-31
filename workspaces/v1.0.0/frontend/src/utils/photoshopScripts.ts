/**
 * Legacy Photoshop JSX is intentionally plain ASCII so it can be run from
 * File > Scripts > Browse on both Windows and macOS Photoshop installs.
 * The script keeps a hidden paragraph backup before converting Houmi-managed
 * text layers to Point Text.
 */
export const HOUMI_POINT_TEXT_CONVERTER_SCRIPT = `#target photoshop
(function () {
  if (!app.documents.length) {
    alert("Open a Houmi PSD first.");
    return;
  }

  var doc = app.activeDocument;
  var changed = 0;

  function visit(container) {
    for (var i = container.layers.length - 1; i >= 0; i--) {
      var layer = container.layers[i];
      if (layer.typename === "LayerSet") {
        visit(layer);
        continue;
      }
      if (layer.typename !== "ArtLayer" || layer.kind !== LayerKind.TEXT) continue;
      if (layer.name.indexOf("TL ") !== 0) continue;

      var backup = layer.duplicate();
      backup.name = "HOUMI_BACKUP " + layer.name;
      backup.visible = false;
      layer.textItem.kind = TextType.POINTTEXT;
      changed++;
    }
  }

  visit(doc);
  alert("Houmi: converted " + changed + " text layer(s) to Point Text.\nHidden paragraph backups were kept.");
}());
`;

export const downloadPhotoshopPointTextConverter = () => {
  const blob = new Blob([HOUMI_POINT_TEXT_CONVERTER_SCRIPT], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'houmi_convert_point_text.jsx';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
};
