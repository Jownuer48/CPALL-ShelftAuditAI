import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

class CameraCaptureScreen extends StatefulWidget {
  const CameraCaptureScreen({super.key});

  @override
  State<CameraCaptureScreen> createState() => _CameraCaptureScreenState();
}

class _CameraCaptureScreenState extends State<CameraCaptureScreen> {
  CameraController? _controller;
  Future<void>? _initFuture;

  bool _isTaking = false;
  bool _flashOn = false;

  @override
  void initState() {
    super.initState();
    _setupCamera();
  }

  Future<void> _setupCamera() async {
    final cameras = await availableCameras();

    final backCamera = cameras.firstWhere(
      (camera) => camera.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );

    final controller = CameraController(
      backCamera,
      ResolutionPreset.high,
      enableAudio: false,
    );

    _controller = controller;
    _initFuture = controller.initialize();

    await _initFuture;

    await controller.setFlashMode(FlashMode.off);

    if (mounted) {
      setState(() {});
    }
  }

  Future<void> _toggleFlash() async {
    if (_controller == null) return;

    setState(() {
      _flashOn = !_flashOn;
    });

    await _controller!.setFlashMode(_flashOn ? FlashMode.torch : FlashMode.off);
  }

  Future<void> _takePicture() async {
    if (_controller == null || _isTaking) return;

    try {
      setState(() {
        _isTaking = true;
      });

      await _initFuture;

      final image = await _controller!.takePicture();

      if (!mounted) return;

      Navigator.pop(context, image);
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('ถ่ายรูปไม่สำเร็จ: $e')));
    } finally {
      if (mounted) {
        setState(() {
          _isTaking = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _controller?.setFlashMode(FlashMode.off);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;

    return Scaffold(
      backgroundColor: const Color(0xFF050505),
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),

            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(22),
                  child: Container(
                    color: Colors.black,
                    child: controller == null || _initFuture == null
                        ? const Center(
                            child: CircularProgressIndicator(
                              color: Colors.white,
                            ),
                          )
                        : FutureBuilder<void>(
                            future: _initFuture,
                            builder: (context, snapshot) {
                              if (snapshot.connectionState !=
                                  ConnectionState.done) {
                                return const Center(
                                  child: CircularProgressIndicator(
                                    color: Colors.white,
                                  ),
                                );
                              }

                              return Stack(
                                fit: StackFit.expand,
                                children: [
                                  _buildCameraPreview(controller),
                                  const ShelfFrameOverlay(),
                                ],
                              );
                            },
                          ),
                  ),
                ),
              ),
            ),

            _buildInstruction(),

            _buildBottomBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close, color: Colors.white, size: 30),
          ),
          const Expanded(
            child: Text(
              'ถ่ายภาพเชลฟ์',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
          IconButton(
            onPressed: _toggleFlash,
            icon: Icon(
              _flashOn ? Icons.flash_on : Icons.flash_off,
              color: Colors.white,
              size: 28,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCameraPreview(CameraController controller) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final previewSize = controller.value.previewSize;

        if (previewSize == null) {
          return const Center(
            child: CircularProgressIndicator(color: Colors.white),
          );
        }

        return FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: previewSize.height,
            height: previewSize.width,
            child: CameraPreview(controller),
          ),
        );
      },
    );
  }

  Widget _buildInstruction() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF111827),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white12),
        ),
        child: const Column(
          children: [
            Text(
              'จัดเชลฟ์ให้อยู่ในกรอบสีเขียว',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 15.5,
                fontWeight: FontWeight.w900,
              ),
            ),
            SizedBox(height: 5),
            Text(
              'ให้เห็นครบทั้งแผง ถ่ายตรงที่สุด และหลีกเลี่ยงการเอียง',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white70,
                fontSize: 13,
                height: 1.35,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          GestureDetector(
            onTap: _isTaking ? null : _takePicture,
            child: Container(
              width: 82,
              height: 82,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 5),
              ),
              child: Center(
                child: Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _isTaking ? Colors.grey : Colors.white,
                  ),
                  child: _isTaking
                      ? const Padding(
                          padding: EdgeInsets.all(16),
                          child: CircularProgressIndicator(strokeWidth: 3),
                        )
                      : null,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class ShelfFrameOverlay extends StatelessWidget {
  const ShelfFrameOverlay({super.key});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: ShelfFramePainter(),
      child: const SizedBox.expand(),
    );
  }
}

class ShelfFramePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final frameWidth = size.width * 0.90;
    final frameHeight = size.height * 0.58;

    final left = (size.width - frameWidth) / 2;
    final top = (size.height - frameHeight) / 2;

    final frameRect = Rect.fromLTWH(left, top, frameWidth, frameHeight);

    final rrect = RRect.fromRectAndRadius(frameRect, const Radius.circular(20));

    final fullPath = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));

    final framePath = Path()..addRRect(rrect);

    final darkPath = Path.combine(
      PathOperation.difference,
      fullPath,
      framePath,
    );

    final darkPaint = Paint()
      ..color = Colors.black.withOpacity(0.50)
      ..style = PaintingStyle.fill;

    canvas.drawPath(darkPath, darkPaint);

    final borderPaint = Paint()
      ..color = const Color(0xFF22FF8A)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.5;

    canvas.drawRRect(rrect, borderPaint);

    final cornerPaint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 7
      ..strokeCap = StrokeCap.round;

    const len = 42.0;

    final l = frameRect.left;
    final t = frameRect.top;
    final r = frameRect.right;
    final b = frameRect.bottom;

    canvas.drawLine(Offset(l, t), Offset(l + len, t), cornerPaint);
    canvas.drawLine(Offset(l, t), Offset(l, t + len), cornerPaint);

    canvas.drawLine(Offset(r, t), Offset(r - len, t), cornerPaint);
    canvas.drawLine(Offset(r, t), Offset(r, t + len), cornerPaint);

    canvas.drawLine(Offset(l, b), Offset(l + len, b), cornerPaint);
    canvas.drawLine(Offset(l, b), Offset(l, b - len), cornerPaint);

    canvas.drawLine(Offset(r, b), Offset(r - len, b), cornerPaint);
    canvas.drawLine(Offset(r, b), Offset(r, b - len), cornerPaint);

    final gridPaint = Paint()
      ..color = Colors.white.withOpacity(0.30)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    final x1 = frameRect.left + frameRect.width / 3;
    final x2 = frameRect.left + frameRect.width * 2 / 3;
    final y1 = frameRect.top + frameRect.height / 3;
    final y2 = frameRect.top + frameRect.height * 2 / 3;

    canvas.drawLine(
      Offset(x1, frameRect.top),
      Offset(x1, frameRect.bottom),
      gridPaint,
    );
    canvas.drawLine(
      Offset(x2, frameRect.top),
      Offset(x2, frameRect.bottom),
      gridPaint,
    );
    canvas.drawLine(
      Offset(frameRect.left, y1),
      Offset(frameRect.right, y1),
      gridPaint,
    );
    canvas.drawLine(
      Offset(frameRect.left, y2),
      Offset(frameRect.right, y2),
      gridPaint,
    );

    final labelPaint = Paint()
      ..color = const Color(0xFF22FF8A)
      ..style = PaintingStyle.fill;

    final labelRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(frameRect.left + 14, frameRect.top + 14, 178, 32),
      const Radius.circular(999),
    );

    canvas.drawRRect(labelRect, labelPaint);

    const textSpan = TextSpan(
      text: 'SHELF AREA',
      style: TextStyle(
        color: Colors.black,
        fontSize: 14,
        fontWeight: FontWeight.w900,
      ),
    );

    final textPainter = TextPainter(
      text: textSpan,
      textDirection: TextDirection.ltr,
    );

    textPainter.layout();

    textPainter.paint(canvas, Offset(frameRect.left + 28, frameRect.top + 21));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
