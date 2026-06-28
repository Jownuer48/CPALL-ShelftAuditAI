import 'package:dio/dio.dart';

import 'captured_shelf_image.dart';
import 'inspection_models.dart';

const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://10.0.2.2:8000',
);

class ApiService {
  ApiService()
    : _dio = Dio(
        BaseOptions(
          baseUrl: apiBaseUrl,
          connectTimeout: const Duration(seconds: 20),
          receiveTimeout: const Duration(seconds: 30),
          headers: const {'ngrok-skip-browser-warning': 'true'},
        ),
      );

  final Dio _dio;

  Future<Inspection> uploadInspection({
    required String branchCode,
    required CapturedShelfImage image,
  }) async {
    final multipartFile = MultipartFile.fromBytes(
      image.bytes,
      filename: image.name.isNotEmpty
          ? image.name
          : 'shelf_${DateTime.now().millisecondsSinceEpoch}.jpg',
    );

    final formData = FormData.fromMap({
      'branch_code': branchCode,
      'file': multipartFile,
    });

    final response = await _dio.post<dynamic>(
      '/upload',
      data: formData,
      options: Options(
        contentType: 'multipart/form-data',
        sendTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
      ),
    );

    return Inspection.fromJson(asMap(response.data));
  }

  Future<Inspection> fetchInspection(int id) async {
    final response = await _dio.get<dynamic>('/inspections/$id');
    return Inspection.fromJson(asMap(response.data));
  }

  Future<List<Inspection>> fetchInspections({int limit = 100}) async {
    final response = await _dio.get<dynamic>(
      '/results',
      queryParameters: {'limit': limit},
    );
    final data = response.data;

    if (data is List) {
      return data.map((item) => Inspection.fromJson(asMap(item))).toList();
    }

    if (data is Map) {
      final items =
          asMap(data)['results'] ?? asMap(data)['items'] ?? asMap(data)['data'];
      if (items is List) {
        return items.map((item) => Inspection.fromJson(asMap(item))).toList();
      }
    }

    return [];
  }

  String? resolveFileUrl(String? value) {
    final raw = cleanString(value);
    if (raw == null) return null;
    if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;

    final base = apiBaseUrl.endsWith('/')
        ? apiBaseUrl.substring(0, apiBaseUrl.length - 1)
        : apiBaseUrl;
    final path = raw.startsWith('/') ? raw : '/$raw';
    return '$base$path';
  }
}

String friendlyError(DioException error) {
  final data = error.response?.data;
  if (data is Map && data['detail'] != null) {
    final detail = data['detail'];
    if (detail is Map && detail['message'] != null) {
      return detail['message'].toString();
    }
    return detail.toString();
  }

  if (error.response != null) {
    return 'Server error ${error.response?.statusCode}. Please try again.';
  }

  return error.message ?? 'Unable to connect to Shelf Audit API.';
}
