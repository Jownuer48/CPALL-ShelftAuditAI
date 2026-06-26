import 'dart:typed_data';

class CapturedShelfImage {
  const CapturedShelfImage({
    required this.name,
    required this.bytes,
    this.path,
  });

  final String name;
  final Uint8List bytes;
  final String? path;
}
