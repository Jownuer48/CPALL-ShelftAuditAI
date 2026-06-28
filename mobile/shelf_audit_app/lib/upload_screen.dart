import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'api_service.dart';
import 'app_theme.dart';
import 'camera_capture_screen_stub.dart'
    if (dart.library.io) 'camera_capture_screen.dart';
import 'captured_shelf_image.dart';
import 'inspection_models.dart';
import 'result_history_screens.dart';
import 'shared_widgets.dart';

class UploadScreen extends StatefulWidget {
  const UploadScreen({required this.api, super.key});

  final ApiService api;

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final TextEditingController _branchController = TextEditingController(
    text: 'STORE-001',
  );
  final ImagePicker _picker = ImagePicker();

  CapturedShelfImage? _selectedImage;
  Timer? _pollTimer;
  Inspection? _inspection;
  String? _message;
  String? _errorMessage;

  bool _isUploading = false;
  bool _isPolling = false;
  bool _isPollingRequest = false;

  bool get _isBusy => _isUploading || _isPolling;

  @override
  void dispose() {
    _pollTimer?.cancel();
    _branchController.dispose();
    super.dispose();
  }

  Future<void> _chooseImage() async {
    if (_isBusy) return;
    final picked = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 92,
    );
    if (picked == null) return;

    final bytes = await picked.readAsBytes();
    if (!mounted) return;
    setState(() {
      _selectedImage = CapturedShelfImage(
        name: picked.name,
        bytes: bytes,
        path: picked.path,
      );
      _inspection = null;
      _errorMessage = null;
      _message = 'Shelf image is ready for inspection.';
    });
  }

  Future<void> _takePhoto() async {
    if (_isBusy) return;

    CapturedShelfImage? captured;
    if (kIsWeb) {
      final picked = await _picker.pickImage(
        source: ImageSource.camera,
        imageQuality: 92,
      );
      if (picked == null) return;
      final bytes = await picked.readAsBytes();
      captured = CapturedShelfImage(
        name: picked.name,
        bytes: bytes,
        path: picked.path,
      );
    } else {
      captured = await Navigator.of(context).push<CapturedShelfImage>(
        MaterialPageRoute(builder: (_) => const CameraCaptureScreen()),
      );
    }

    if (!mounted || captured == null) return;
    setState(() {
      _selectedImage = captured;
      _inspection = null;
      _errorMessage = null;
      _message = 'Shelf photo captured and ready.';
    });
  }

  Future<void> _uploadImage() async {
    final image = _selectedImage;
    if (image == null) {
      setState(
        () => _errorMessage = 'Please choose or capture a shelf image first.',
      );
      return;
    }

    FocusScope.of(context).unfocus();
    _stopPolling();
    setState(() {
      _isUploading = true;
      _inspection = null;
      _errorMessage = null;
      _message = 'Uploading shelf image...';
    });

    try {
      final inspection = await widget.api.uploadInspection(
        branchCode: _branchController.text.trim().isEmpty
            ? 'STORE-001'
            : _branchController.text.trim(),
        image: image,
      );

      if (!mounted) return;
      setState(() {
        _inspection = inspection;
        _message = inspection.isPending
            ? 'Inspection queued. Waiting for AI worker...'
            : 'Inspection result is ready.';
      });

      final id = inspection.id;
      if (id != null && inspection.isPending) {
        _startPolling(id);
      }
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = friendlyError(error));
    } catch (error) {
      if (!mounted) return;
      setState(() => _errorMessage = 'Unable to upload image: $error');
    } finally {
      if (mounted) setState(() => _isUploading = false);
    }
  }

  void _startPolling(int inspectionId) {
    _pollTimer?.cancel();
    setState(() => _isPolling = true);
    _pollTimer = Timer.periodic(
      const Duration(seconds: 3),
      (_) => _fetchInspection(inspectionId),
    );
    unawaited(_fetchInspection(inspectionId));
  }

  Future<void> _fetchInspection(int inspectionId) async {
    if (_isPollingRequest) return;
    _isPollingRequest = true;

    try {
      final inspection = await widget.api.fetchInspection(inspectionId);
      if (!mounted) return;
      setState(() {
        _inspection = inspection;
        _message = inspection.isPending
            ? 'AI worker is still analyzing...'
            : 'Inspection result is ready.';
      });

      if (!inspection.isPending) {
        _stopPolling();
      }
    } on DioException catch (error) {
      if (mounted) {
        setState(() => _errorMessage = friendlyError(error));
      }
    } catch (error) {
      if (mounted) {
        setState(() => _errorMessage = 'Unable to refresh inspection: $error');
      }
    } finally {
      _isPollingRequest = false;
    }
  }

  void _stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
    if (mounted) setState(() => _isPolling = false);
  }

  void _openResult(Inspection inspection) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) =>
            ResultDetailScreen(api: widget.api, inspection: inspection),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final selectedImage = _selectedImage;
    final canSubmit = selectedImage != null && !_isBusy;

    return Scaffold(
      appBar: AppBar(
        title: const Text('New Inspection'),
        actions: [
          IconButton(
            onPressed: _isBusy ? null : () => Navigator.of(context).pop(),
            icon: const Icon(Icons.home_outlined),
            tooltip: 'Home',
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
          children: [
            const PageIntro(
              icon: Icons.document_scanner_outlined,
              title: 'Shelf Inspection',
              subtitle:
                  'Capture a clear shelf photo and let AI compare it with the planogram.',
            ),
            const SizedBox(height: 18),
            _buildBranchCard(),
            const SizedBox(height: 16),
            _buildImageCard(selectedImage),
            const SizedBox(height: 16),
            PrimaryButton(
              label: _isUploading ? 'Uploading...' : 'Submit for AI Inspection',
              icon: Icons.cloud_upload_outlined,
              onPressed: canSubmit ? _uploadImage : null,
              isLoading: _isUploading,
            ),
            if (_isPolling || _isUploading) ...[
              const SizedBox(height: 16),
              ProcessingSteps(
                isUploading: _isUploading,
                isPolling: _isPolling,
                inspection: _inspection,
              ),
            ],
            if (_inspection != null) ...[
              const SizedBox(height: 16),
              ResultPreviewCard(
                inspection: _inspection!,
                onOpen: () => _openResult(_inspection!),
              ),
            ],
            if (_message != null && _errorMessage == null) ...[
              const SizedBox(height: 16),
              MessagePanel(message: _message!, isError: false),
            ],
            if (_errorMessage != null) ...[
              const SizedBox(height: 16),
              MessagePanel(message: _errorMessage!, isError: true),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBranchCard() {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionTitle(title: 'Store information'),
          const SizedBox(height: 12),
          TextField(
            controller: _branchController,
            enabled: !_isBusy,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
              labelText: 'Branch code',
              hintText: 'Example: STORE-001',
              prefixIcon: Icon(Icons.storefront_outlined),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildImageCard(CapturedShelfImage? image) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionTitle(title: 'Shelf photo'),
          const SizedBox(height: 12),
          ShelfImagePicker(imageBytes: image?.bytes, fileName: image?.name),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isBusy ? null : _chooseImage,
                  icon: const Icon(Icons.photo_library_outlined),
                  label: const Text('Gallery'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _isBusy ? null : _takePhoto,
                  icon: const Icon(Icons.photo_camera_outlined),
                  label: const Text('Camera'),
                ),
              ),
            ],
          ),
          if (image != null) ...[
            const SizedBox(height: 10),
            Text(
              image.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: AppColors.muted,
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
