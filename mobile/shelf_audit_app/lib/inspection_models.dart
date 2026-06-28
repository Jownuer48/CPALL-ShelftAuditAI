class Inspection {
  Inspection({
    required this.id,
    required this.status,
    required this.result,
    required this.branchCode,
    required this.detectedModel,
    required this.modelScore,
    required this.missingCount,
    required this.missingItems,
    required this.imageUrl,
    required this.annotatedImageUrl,
    required this.errorMessage,
    required this.message,
    required this.productPassRate,
    required this.promoPassRate,
    required this.overallComplianceScore,
    required this.createdAt,
    required this.updatedAt,
  });

  final int? id;
  final String? status;
  final String? result;
  final String? branchCode;
  final String? detectedModel;
  final double? modelScore;
  final int missingCount;
  final List<MissingItem> missingItems;
  final String? imageUrl;
  final String? annotatedImageUrl;
  final String? errorMessage;
  final String? message;
  final double? productPassRate;
  final double? promoPassRate;
  final double? overallComplianceScore;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory Inspection.fromJson(Map<String, dynamic> json) {
    final missing = json['missing_items'];
    return Inspection(
      id: parseInt(json['inspection_id'] ?? json['id']),
      status: cleanString(json['status']),
      result: cleanString(json['result']),
      branchCode: cleanString(json['branch_code']),
      detectedModel: cleanString(json['detected_model']),
      modelScore: parseDouble(json['model_score']),
      missingCount: parseInt(json['missing_count']) ?? 0,
      missingItems: missing is List
          ? missing.map((item) => MissingItem.fromJson(asMap(item))).toList()
          : <MissingItem>[],
      imageUrl: cleanString(json['image_url']),
      annotatedImageUrl: cleanString(json['annotated_image_url']),
      errorMessage: cleanString(json['error_message']),
      message: cleanString(json['message']),
      productPassRate: parseDouble(json['product_pass_rate']),
      promoPassRate: parseDouble(json['promo_pass_rate']),
      overallComplianceScore: parseDouble(json['overall_compliance_score']),
      createdAt: parseDate(json['created_at']),
      updatedAt: parseDate(json['updated_at']),
    );
  }

  String get statusText {
    final normalizedStatus = status?.toUpperCase();
    final normalizedResult = result?.toUpperCase();

    if (normalizedStatus == 'DONE' && normalizedResult != null) {
      return normalizedResult;
    }

    if (normalizedResult != null && normalizedResult != 'PENDING') {
      return normalizedResult;
    }

    return normalizedStatus ?? normalizedResult ?? 'PENDING';
  }

  bool get isPending {
    final normalized = statusText;
    return normalized == 'PENDING' ||
        normalized == 'PROCESSING' ||
        normalized == 'QUEUED';
  }

  bool get isPass => statusText == 'PASS';
  bool get isWarning => statusText == 'WARNING';
  bool get isFail => statusText == 'FAIL' || statusText == 'FAILED';
  bool get isRetake =>
      statusText == 'NEED_RETAKE' || statusText == 'UNKNOWN_MODEL';
}

class MissingItem {
  MissingItem({
    required this.slotId,
    required this.productName,
    required this.status,
    required this.expectedCount,
    required this.detectedCount,
    required this.requiredCount,
    required this.appearanceSimilarity,
    required this.reason,
  });

  final String? slotId;
  final String? productName;
  final String? status;
  final int? expectedCount;
  final int? detectedCount;
  final int? requiredCount;
  final double? appearanceSimilarity;
  final String? reason;

  factory MissingItem.fromJson(Map<String, dynamic> json) {
    return MissingItem(
      slotId: cleanString(json['slot_id']),
      productName: cleanString(json['product_name']),
      status: cleanString(json['status']),
      expectedCount: parseInt(json['expected_count']),
      detectedCount: parseInt(json['detected_count']),
      requiredCount: parseInt(json['required_count']),
      appearanceSimilarity: parseDouble(json['appearance_similarity']),
      reason: cleanString(json['reason']),
    );
  }
}

Map<String, dynamic> asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String? cleanString(dynamic value) {
  if (value == null) return null;
  final text = value.toString().trim();
  if (text.isEmpty || text.toLowerCase() == 'null') return null;
  return text;
}

int? parseInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is double) return value.toInt();
  return int.tryParse(value.toString());
}

double? parseDouble(dynamic value) {
  if (value == null) return null;
  if (value is double) return value;
  if (value is int) return value.toDouble();
  return double.tryParse(value.toString());
}

DateTime? parseDate(dynamic value) {
  final text = cleanString(value);
  if (text == null) return null;
  return DateTime.tryParse(text.replaceFirst(' ', 'T'));
}
