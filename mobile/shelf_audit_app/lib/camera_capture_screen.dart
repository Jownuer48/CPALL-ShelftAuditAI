import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'camera_frame_config.dart';

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
  bool _flashAvailable = true;
  String? _cameraError;

  @override
  void initState() {
    super.initState();

    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

    _setupCamera();
  }

  Future<void> _setupCamera() async {
    try {
      final cameras = await availableCameras();

      if (cameras.isEmpty) {
        setState(() {
          _cameraError = 'ไม่พบกล้องบนอุปกรณ์นี้';
        });
        return;
      }

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

      try {
        await controller.lockCaptureOrientation(DeviceOrientation.portraitUp);
      } catch (_) {}

      try {
        await controller.setFlashMode(FlashMode.off);
      } catch (_) {
        _flashAvailable = false;
      }

      if (mounted) {
        setState(() {});
      }
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _cameraError = 'เปิดกล้องไม่สำเร็จ: $e';
      });
    }
  }

  Future<void> _toggleFlash() async {
    final controller = _controller;

    if (controller == null || !_flashAvailable) {
      _showSnackBar('เครื่องนี้ไม่รองรับแฟลชในโหมดกล้องนี้');
      return;
    }

    try {
      final nextFlashState = !_flashOn;

      await controller.setFlashMode(
        nextFlashState ? FlashMode.torch : FlashMode.off,
      );

      if (!mounted) return;

      setState(() {
        _flashOn = nextFlashState;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        _flashAvailable = false;
        _flashOn = false;
      });

      _showSnackBar('เครื่องนี้ไม่รองรับแฟลชในโหมดกล้องนี้');
    }
  }

  Future<void> _takePicture() async {
    final controller = _controller;

    if (controller == null || _isTaking) return;

    try {
      setState(() {
        _isTaking = true;
      });

      await _initFuture;

      final image = await controller.takePicture();

      if (!mounted) return;

      Navigator.pop(context, image);
    } catch (e) {
      if (!mounted) return;

      _showSnackBar('ถ่ายรูปไม่สำเร็จ: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isTaking = false;
        });
      }
    }
  }

  void _showSnackBar(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  void dispose() {
    try {
      _controller?.setFlashMode(FlashMode.off);
    } catch (_) {}

    _controller?.dispose();

    SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

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
                  borderRadius: BorderRadius.circular(
                    CameraFrameConfig.borderRadius,
                  ),
                  child: Container(
                    color: Colors.black,
                    child: _cameraError != null
                        ? _buildCameraError()
                        : controller == null || _initFuture == null
                        ? _buildLoading()
                        : FutureBuilder<void>(
                            future: _initFuture,
                            builder: (context, snapshot) {
                              if (snapshot.connectionState !=
                                  ConnectionState.done) {
                                return _buildLoading();
                              }

                              if (snapshot.hasError) {
                                return _buildCameraError(
                                  message: snapshot.error.toString(),
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
              CameraFrameConfig.title,
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
              color: _flashAvailable ? Colors.white : Colors.white38,
              size: 28,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoading() {
    return const Center(child: CircularProgressIndicator(color: Colors.white));
  }

  Widget _buildCameraError({String? message}) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(22),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.no_photography, color: Colors.white70, size: 56),
            const SizedBox(height: 14),
            const Text(
              'ไม่สามารถเปิดกล้องได้',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w900,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              message ?? _cameraError ?? '-',
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 13,
                height: 1.35,
              ),
            ),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: () {
                setState(() {
                  _cameraError = null;
                  _controller = null;
                  _initFuture = null;
                });

                _setupCamera();
              },
              icon: const Icon(Icons.refresh),
              label: const Text('ลองใหม่'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCameraPreview(CameraController controller) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final previewSize = controller.value.previewSize;

        if (previewSize == null) {
          return _buildLoading();
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
        child: const Text(
          CameraFrameConfig.instruction,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Colors.white,
            fontSize: 14.5,
            fontWeight: FontWeight.w800,
            height: 1.35,
          ),
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
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              width: _isTaking ? 76 : 84,
              height: _isTaking ? 76 : 84,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 5),
              ),
              child: Center(
                child: Container(
                  width: _isTaking ? 48 : 60,
                  height: _isTaking ? 48 : 60,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _isTaking ? Colors.grey : Colors.white,
                  ),
                  child: _isTaking
                      ? const Padding(
                          padding: EdgeInsets.all(12),
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
    final frameWidth = size.width * CameraFrameConfig.frameWidthRatio;
    final frameHeight = size.height * CameraFrameConfig.frameHeightRatio;

    final left = (size.width - frameWidth) / 2;
    final top = size.height * CameraFrameConfig.frameTopRatio;

    final frameRect = Rect.fromLTWH(left, top, frameWidth, frameHeight);

    final rrect = RRect.fromRectAndRadius(
      frameRect,
      const Radius.circular(CameraFrameConfig.borderRadius),
    );

    final fullPath = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));

    final framePath = Path()..addRRect(rrect);

    final darkPath = Path.combine(
      PathOperation.difference,
      fullPath,
      framePath,
    );

    final darkPaint = Paint()
      ..color = Colors.black.withOpacity(CameraFrameConfig.overlayOpacity)
      ..style = PaintingStyle.fill;

    canvas.drawPath(darkPath, darkPaint);

    final borderPaint = Paint()
      ..color = CameraFrameConfig.frameColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = CameraFrameConfig.borderWidth;

    canvas.drawRRect(rrect, borderPaint);

    _drawCorners(canvas, frameRect);
    _drawGrid(canvas, frameRect);
    _drawLabel(canvas, frameRect);
  }

  void _drawCorners(Canvas canvas, Rect frameRect) {
    final cornerPaint = Paint()
      ..color = CameraFrameConfig.cornerColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = CameraFrameConfig.cornerWidth
      ..strokeCap = StrokeCap.round;

    const len = CameraFrameConfig.cornerLength;

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
  }

  void _drawGrid(Canvas canvas, Rect frameRect) {
    if (!CameraFrameConfig.showGrid) return;

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

    if (!CameraFrameConfig.showCenterLine) return;

    final centerPaint = Paint()
      ..color = CameraFrameConfig.frameColor.withOpacity(0.45)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    canvas.drawLine(
      Offset(frameRect.center.dx, frameRect.top),
      Offset(frameRect.center.dx, frameRect.bottom),
      centerPaint,
    );

    canvas.drawLine(
      Offset(frameRect.left, frameRect.center.dy),
      Offset(frameRect.right, frameRect.center.dy),
      centerPaint,
    );
  }

  void _drawLabel(Canvas canvas, Rect frameRect) {
    final labelPaint = Paint()
      ..color = CameraFrameConfig.frameColor
      ..style = PaintingStyle.fill;

    final labelRect = RRect.fromRectAndRadius(
      Rect.fromLTWH(frameRect.left + 14, frameRect.top + 14, 136, 32),
      const Radius.circular(999),
    );

    canvas.drawRRect(labelRect, labelPaint);

    const textSpan = TextSpan(
      text: 'SHELF AREA',
      style: TextStyle(
        color: Colors.black,
        fontSize: 13,
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
