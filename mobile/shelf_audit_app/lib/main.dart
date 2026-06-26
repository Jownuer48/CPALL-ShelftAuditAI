import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'camera_capture_screen.dart';

const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);

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
  final Dio _dio = Dio();

  CapturedShelfImage? _selectedImage;
  Uint8List? _selectedImageBytes;
  Timer? _pollTimer;

  bool _isUploading = false;
  bool _isPolling = false;
  bool _isPollingRequest = false;

  int? _inspectionId;
  String? _status;
  String? _result;
  String? _detectedModel;
  double? _modelScore;
  int? _missingCount;
  List<dynamic> _missingItems = [];
  String? _message;
  String? _errorMessage;

  @override
  void dispose() {
    _pollTimer?.cancel();
    _branchController.dispose();
    super.dispose();
  }

  Future<void> _takePhoto() async {
    final image = await Navigator.push<CapturedShelfImage?>(
      context,
      MaterialPageRoute(builder: (_) => const CameraCaptureScreen()),
    );

    if (image == null) return;

    setState(() {
      _selectedImage = image;
      _selectedImageBytes = image.bytes;
      _clearResult();
    });
  }

  void _clearResult() {
    _pollTimer?.cancel();
    _pollTimer = null;
    _isPolling = false;
    _isPollingRequest = false;
    _inspectionId = null;
    _status = null;
    _result = null;
    _detectedModel = null;
    _modelScore = null;
    _missingCount = null;
    _missingItems = [];
    _message = null;
    _errorMessage = null;
  }

  Future<void> _uploadImage() async {
    final branchCode = _branchController.text.trim();

    if (branchCode.isEmpty) {
      _showSnackBar('กรุณากรอกรหัสสาขา');
      return;
    }

    if (_selectedImage == null || _selectedImageBytes == null) {
      _showSnackBar('กรุณาถ่ายรูปก่อน');
      return;
    }

    setState(() {
      _isUploading = true;
      _message = null;
      _errorMessage = null;
    });

    try {
      final fileName = _selectedImage!.name.isNotEmpty
          ? _selectedImage!.name
          : 'shelf_${DateTime.now().millisecondsSinceEpoch}.jpg';

      final multipartFile = MultipartFile.fromBytes(
        _selectedImageBytes!,
        filename: fileName,
      );

      final formData = FormData.fromMap({
        'branch_code': branchCode,
        'file': multipartFile,
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

      final data = _asMap(response.data);
      final inspectionId = _parseInt(data['inspection_id'] ?? data['id']);

      setState(() {
        _applyInspectionData(data);
        _message = data['message']?.toString() ?? 'Upload received. Analysis is queued.';
      });

      if (inspectionId != null && !_isTerminalStatus(_status)) {
        _startPolling(inspectionId);
      }
    } on DioException catch (e) {
      setState(() {
        _message = _dioErrorText(e);
        _status = 'FAILED';
        _errorMessage = _message;
      });
    } catch (e) {
      setState(() {
        _message = 'Error: $e';
        _status = 'FAILED';
        _errorMessage = _message;
      });
    } finally {
      if (mounted) {
        setState(() {
          _isUploading = false;
        });
      }
    }
  }

  void _startPolling(int inspectionId) {
    _pollTimer?.cancel();

    if (mounted) {
      setState(() {
        _isPolling = true;
      });
    } else {
      _isPolling = true;
    }

    _fetchInspection(inspectionId);
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      _fetchInspection(inspectionId);
    });
  }

  Future<void> _fetchInspection(int inspectionId) async {
    if (_isPollingRequest) return;

    _isPollingRequest = true;

    try {
      final response = await _dio.get(
        '$apiBaseUrl/inspections/$inspectionId',
        options: Options(headers: {'ngrok-skip-browser-warning': 'true'}),
      );

      if (!mounted) return;

      final data = _asMap(response.data);

      setState(() {
        _applyInspectionData(data);
      });

      if (_isTerminalStatus(_status)) {
        _stopPolling(notify: true);
      }
    } on DioException catch (e) {
      if (!mounted) return;

      setState(() {
        _message = _dioErrorText(e);
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _message = 'Polling error: $e';
      });
    } finally {
      _isPollingRequest = false;
    }
  }

  void _stopPolling({bool notify = false}) {
    _pollTimer?.cancel();
    _pollTimer = null;

    if (notify && mounted) {
      setState(() {
        _isPolling = false;
      });
    } else {
      _isPolling = false;
    }
  }

  void _applyInspectionData(Map<String, dynamic> data) {
    _inspectionId = _parseInt(data['inspection_id'] ?? data['id']) ?? _inspectionId;
    _status = _cleanString(data['status']) ?? _status;
    _result = _cleanString(data['result']) ?? _result;
    _detectedModel = _cleanString(data['detected_model']);
    _modelScore = _parseDouble(data['model_score']);
    _missingCount = _parseInt(data['missing_count']);
    _missingItems = data['missing_items'] is List ? data['missing_items'] : [];
    _errorMessage = _cleanString(data['error_message']);

    if (_status == 'FAILED' && _errorMessage != null) {
      _message = _errorMessage;
    }
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return {};
  }

  String? _cleanString(dynamic value) {
    if (value == null) return null;
    final text = value.toString();
    if (text.isEmpty || text == 'null') return null;
    return text;
  }

  String _dioErrorText(DioException e) {
    final responseData = e.response?.data;

    if (responseData is Map && responseData['detail'] != null) {
      final detail = responseData['detail'];
      if (detail is Map && detail['message'] != null) {
        return detail['message'].toString();
      }
      return detail.toString();
    }

    if (e.response != null) {
      return 'Server Error: ${e.response?.statusCode}';
    }

    return e.message ?? 'Upload failed';
  }

  bool _isTerminalStatus(String? status) {
    return status == 'DONE' || status == 'FAILED';
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

  Color _statusColor() {
    if (_status == 'FAILED') return Colors.red;
    if (_status == 'PROCESSING') return Colors.blue;
    if (_status == 'PENDING') return Colors.orange;

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

  String _displayResultText() {
    if (_status == 'DONE') return _result ?? 'DONE';
    return _status ?? _result ?? '-';
  }

  bool get _hasImage => _selectedImage != null && _selectedImageBytes != null;
  bool get _hasInspection => _status != null || _result != null || _inspectionId != null;

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
              if (_hasInspection) _buildResultCard(),
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
            if (!_hasImage)
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
                      Text('ยังไม่ได้ถ่ายรูปภาพ'),
                    ],
                  ),
                ),
              )
            else
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.memory(
                  _selectedImageBytes!,
                  height: 280,
                  fit: BoxFit.cover,
                ),
              ),
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: _isUploading || _isPolling ? null : _takePhoto,
              icon: const Icon(Icons.camera_alt),
              label: const Text('ถ่ายรูป'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUploadButton() {
    final isBusy = _isUploading || _isPolling;

    return FilledButton.icon(
      onPressed: isBusy ? null : _uploadImage,
      icon: isBusy
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.cloud_upload),
      label: Text(
        _isUploading
            ? 'กำลังส่งข้อมูล...'
            : _isPolling
            ? 'กำลังตรวจด้วย AI...'
            : 'ส่งตรวจด้วย AI',
      ),
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 16),
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
      ),
    );
  }

  Widget _buildResultCard() {
    final color = _statusColor();

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
              _displayResultText(),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 34,
                fontWeight: FontWeight.w900,
                color: color,
              ),
            ),
            const SizedBox(height: 12),
            _infoRow('Inspection ID', '${_inspectionId ?? '-'}'),
            _infoRow('Status', _status ?? '-'),
            _infoRow('Detected Model', _detectedModel ?? '-'),
            _infoRow('Model Score', _scoreText()),
            _infoRow('Missing Count', '${_missingCount ?? 0}'),
            if (_errorMessage != null) ...[
              const SizedBox(height: 8),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.red,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
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
    final message = _message ?? '';
    final isError =
        _status == 'FAILED' ||
        message.toLowerCase().contains('error') ||
        message.toLowerCase().contains('failed') ||
        message.toLowerCase().contains('server');

    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Text(
        message,
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
