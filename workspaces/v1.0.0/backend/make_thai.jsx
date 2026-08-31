var doc = app.documents.add(720, 1000, 72, "Thai_Native_PS2026", NewDocumentMode.RGB, DocumentFill.WHITE);
var textLayer = doc.artLayers.add();
textLayer.kind = LayerKind.TEXT;
var textItem = textLayer.textItem;
textItem.contents = "เจ้าแห่งบัลลังก์เทพสุริยัน\nแห่งเชี่ยกั้ว [ผู้ผนึก]\nผู้มีชื่อเสียงอันน่าพรั่นพรึง\nได้เดินทางมาถึงประเทศ A\nเป็นครั้งแรก!!";
textItem.font = "THBaijam-Bold";
textItem.size = new UnitValue(38, "pt");
textItem.position = [new UnitValue(100, "px"), new UnitValue(200, "px")];

var psdSaveOptions = new PhotoshopSaveOptions();
psdSaveOptions.embedColorProfile = true;
psdSaveOptions.alphaChannels = true;
psdSaveOptions.layers = true;

var saveFile = new File("E:/houmi/backend/native_ps2026_thai.psd");
doc.saveAs(saveFile, psdSaveOptions, true, Extension.LOWERCASE);
doc.close(SaveOptions.DONOTSAVECHANGES);
