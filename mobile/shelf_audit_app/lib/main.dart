import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

void main() {
  runApp(const ShelfAuditApp());
}

class ShelfAuditApp extends StatelessWidget {
  const ShelfAuditApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Shelf Audit AI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: Colors.green,
        scaffoldBackgroundColor: const Color(0xFFF4F7F5),
      ),
      home: const UploadScreen(),
    );
  }
}

class UploadScreen extends StatefulWidget {
  const UploadScreen({super.key});

  @override
  State<UploadScreen> createState() => _UploadScreenState();
}

class _UploadScreenState extends State<UploadScreen> {
  final TextEditingController _branchController = TextEditingController();
  final ImagePicker _picker = ImagePicker();
  final Dio _dio = Dio();

  XFile? _selectedImage;
  bool _isUploading = false;

  String? _result;
  String? _detectedModel;
  double? _modelScore;
  int? _missingCount;
  List<dynamic> _missingItems = [];
  String? _message;

  Future<void> _takePhoto() async {
    final XFile? image = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
      maxWidth: 1280,
    );

    if (image == null) return;

    setState(() {
      _selectedImage = image;
      _clearResult();
    });
  }

  Future<void> _pickFromGallery() async {
    final XFile? image = await _picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 85,
      maxWidth: 1280,
    );

    if (image == null) return;

    setState(() {
      _selectedImage = image;
      _clearResult();
    });
  }

  void _clearResult() {
    _result = null;
    _detectedModel = null;
    _modelScore = null;
    _missingCount = null;
    _missingItems = [];
    _message = null;
  }

  Future<void> _uploadImage() async {
    final branchCode = _branchController.text.trim();

    if (branchCode.isEmpty) {
      _showSnackBar('กรุณากรอกรหัสสาขา');
      return;
    }

    if (_selectedImage == null) {
      _showSnackBar('กรุณาถ่ายรูปหรือเลือกรูปก่อน');
      return;
    }

    setState(() {
      _isUploading = true;
      _message = null;
    });

    try {
      final formData = FormData.fromMap({
        'branch_code': branchCode,
        'file': await MultipartFile.fromFile(
          _selectedImage!.path,
          filename: _selectedImage!.name,
        ),
      });

      final response = await _dio.post(
        '$apiBaseUrl/upload',
        data: formData,
        options: Options(
          contentType: 'multipart/form-data',
          sendTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 30),
          headers: {'ngrok-skip-browser-warning': 'true'},
        ),
      );

      final data = response.data;

      setState(() {
        _result = data['result']?.toString();
        _detectedModel = data['detected_model']?.toString();
        _modelScore = _parseDouble(data['model_score']);
        _missingCount = _parseInt(data['missing_count']);
        _missingItems = data['missing_items'] is List
            ? data['missing_items']
            : [];
        _message = data['message']?.toString() ?? 'Upload success';
      });
    } on DioException catch (e) {
      String errorText = 'Upload failed';

      if (e.response != null) {
        errorText = 'Server Error: ${e.response?.statusCode}';
      } else if (e.message != null) {
        errorText = e.message!;
      }

      setState(() {
        _message = errorText;
      });
    } catch (e) {
      setState(() {
        _message = 'Error: $e';
      });
    } finally {
      setState(() {
        _isUploading = false;
      });
    }
  }

  double? _parseDouble(dynamic value) {
    if (value == null) return null;
    if (value is double) return value;
    if (value is int) return value.toDouble();
    return double.tryParse(value.toString());
  }

  int? _parseInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    return int.tryParse(value.toString());
  }

  void _showSnackBar(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Color _resultColor() {
    final result = _result?.toUpperCase();

    if (result == 'PASS') return Colors.green;
    if (result == 'FAIL') return Colors.red;
    if (result == 'UNKNOWN_MODEL') return Colors.orange;

    return Colors.grey;
  }

  String _scoreText() {
    if (_modelScore == null) return '-';
    return '${(_modelScore! * 100).toStringAsFixed(2)}%';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Shelf Audit AI'), centerTitle: true),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _buildBranchCard(),
              const SizedBox(height: 16),
              _buildImageCard(),
              const SizedBox(height: 16),
              _buildUploadButton(),
              const SizedBox(height: 16),
              if (_result != null) _buildResultCard(),
              if (_message != null) _buildMessage(),
              const SizedBox(height: 20),
              _buildApiInfo(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBranchCard() {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'ข้อมูลสาขา',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: _branchController,
              keyboardType: TextInputType.text,
              decoration: InputDecoration(
                labelText: 'รหัสสาขา',
                hintText: 'เช่น 0001',
                prefixIcon: const Icon(Icons.store),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImageCard() {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'รูปภาพเชลฟ์',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 14),
            if (_selectedImage == null)
              Container(
                height: 230,
                decoration: BoxDecoration(
                  color: Colors.grey.shade200,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.grey.shade300),
                ),
                child: const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.image, size: 58, color: Colors.grey),
                      SizedBox(height: 8),
                      Text('ยังไม่ได้เลือกรูปภาพ'),
                    ],
                  ),
                ),
              )
            else
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.file(
                  File(_selectedImage!.path),
                  height: 280,
                  fit: BoxFit.cover,
                ),
              ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _isUploading ? null : _takePhoto,
                    icon: const Icon(Icons.camera_alt),
                    label: const Text('ถ่ายรูป'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _isUploading ? null : _pickFromGallery,
                    icon: const Icon(Icons.photo_library),
                    label: const Text('เลือกรูป'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUploadButton() {
    return FilledButton.icon(
      onPressed: _isUploading ? null : _uploadImage,
      icon: _isUploading
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.cloud_upload),
      label: Text(_isUploading ? 'กำลังส่งข้อมูล...' : 'ส่งตรวจด้วย AI'),
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 16),
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
      ),
    );
  }

  Widget _buildResultCard() {
    final color = _resultColor();

    return Card(
      elevation: 0,
      color: color.withOpacity(0.10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: color, width: 1.4),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _result ?? '-',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 34,
                fontWeight: FontWeight.w900,
                color: color,
              ),
            ),
            const SizedBox(height: 12),
            _infoRow('Detected Model', _detectedModel ?? '-'),
            _infoRow('Model Score', _scoreText()),
            _infoRow('Missing Count', '${_missingCount ?? 0}'),
            const SizedBox(height: 12),
            if (_missingItems.isEmpty)
              const Text(
                'Missing Items: ไม่มีรายการ',
                style: TextStyle(fontSize: 15),
              )
            else
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Missing Items',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  ..._missingItems.map((item) {
                    final slotId = item['slot_id']?.toString() ?? '-';
                    final productName = item['product_name']?.toString() ?? '-';
                    final score = item['score']?.toString() ?? '-';

                    return Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.75),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.black12),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '$slotId - $productName',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 4),
                          Text('Score: $score'),
                        ],
                      ),
                    );
                  }),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: Colors.grey.shade700,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }

  Widget _buildMessage() {
    final isError =
        _message!.toLowerCase().contains('error') ||
        _message!.toLowerCase().contains('failed');

    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Text(
        _message!,
        textAlign: TextAlign.center,
        style: TextStyle(
          color: isError ? Colors.red : Colors.green,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildApiInfo() {
    return Text(
      'API: $apiBaseUrl',
      textAlign: TextAlign.center,
      style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
    );
  }
}
