import 'package:flutter/material.dart';

import 'api_service.dart';
import 'app_theme.dart';
import 'inspection_models.dart';
import 'shared_widgets.dart';

class ResultDetailScreen extends StatefulWidget {
  const ResultDetailScreen({
    required this.api,
    required this.inspection,
    super.key,
  });

  final ApiService api;
  final Inspection inspection;

  @override
  State<ResultDetailScreen> createState() => _ResultDetailScreenState();
}

class _ResultDetailScreenState extends State<ResultDetailScreen> {
  late Future<Inspection> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Inspection> _load() {
    final id = widget.inspection.id;
    if (id == null) return Future<Inspection>.value(widget.inspection);
    return widget.api.fetchInspection(id);
  }

  Future<void> _reload() async {
    final next = _load();
    setState(() => _future = next);
    await next;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Inspection Result'),
        actions: [
          IconButton(
            onPressed: _reload,
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: FutureBuilder<Inspection>(
        future: _future,
        initialData: widget.inspection,
        builder: (context, snapshot) {
          if (snapshot.hasError && snapshot.data == null) {
            return ErrorView(
              message: 'Unable to load result.',
              detail: snapshot.error.toString(),
              onRetry: _reload,
            );
          }

          final inspection = snapshot.data;
          if (inspection == null) {
            return const LoadingView(message: 'Loading result...');
          }

          return RefreshIndicator(
            onRefresh: _reload,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 30),
              children: [
                _buildHero(inspection),
                const SizedBox(height: 16),
                _buildImageSection(inspection),
                const SizedBox(height: 16),
                _buildMetrics(inspection),
                const SizedBox(height: 16),
                _buildMissingItems(inspection),
                if (snapshot.hasError) ...[
                  const SizedBox(height: 16),
                  MessagePanel(
                    message:
                        'Showing saved result. Refresh failed: ${snapshot.error}',
                    isError: true,
                  ),
                ],
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildHero(Inspection inspection) {
    final color = statusColor(inspection.statusText);
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Icon(_statusIcon(inspection), color: color, size: 30),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Inspection #${inspection.id ?? '-'}',
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      formatDate(inspection.updatedAt ?? inspection.createdAt),
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              AppStatusBadge(status: inspection.statusText),
            ],
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _InfoPill(
                icon: Icons.storefront_outlined,
                label: 'Branch',
                value: inspection.branchCode ?? '-',
              ),
              _InfoPill(
                icon: Icons.view_module_outlined,
                label: 'Model',
                value: inspection.detectedModel ?? '-',
              ),
              _InfoPill(
                icon: Icons.inventory_2_outlined,
                label: 'Missing',
                value: '${inspection.missingCount}',
              ),
            ],
          ),
          if (inspection.message != null ||
              inspection.errorMessage != null) ...[
            const SizedBox(height: 14),
            MessagePanel(
              message: inspection.errorMessage ?? inspection.message!,
              isError: inspection.errorMessage != null,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildImageSection(Inspection inspection) {
    final url = widget.api.resolveFileUrl(
      inspection.annotatedImageUrl ?? inspection.imageUrl,
    );
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionTitle(title: 'Annotated shelf image'),
          const SizedBox(height: 12),
          if (url == null)
            const EmptyState(
              icon: Icons.image_not_supported_outlined,
              title: 'No image available',
              message:
                  'The API response does not include an image URL for this inspection.',
            )
          else
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: Container(
                constraints: const BoxConstraints(minHeight: 220),
                color: const Color(0xFFF8FBFF),
                child: Image.network(
                  url,
                  width: double.infinity,
                  fit: BoxFit.cover,
                  loadingBuilder: (context, child, progress) {
                    if (progress == null) return child;
                    return const SizedBox(
                      height: 260,
                      child: LoadingView(message: 'Loading image...'),
                    );
                  },
                  errorBuilder: (context, error, stackTrace) {
                    return const SizedBox(
                      height: 220,
                      child: EmptyState(
                        icon: Icons.broken_image_outlined,
                        title: 'Image unavailable',
                        message:
                            'The annotated image could not be loaded from the API.',
                      ),
                    );
                  },
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildMetrics(Inspection inspection) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      childAspectRatio: 1.18,
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      children: [
        MetricTile(
          label: 'Model score',
          value: formatPercent(inspection.modelScore),
          icon: Icons.analytics_outlined,
          color: AppColors.blue,
        ),
        MetricTile(
          label: 'Compliance',
          value: formatPercent(inspection.overallComplianceScore),
          icon: Icons.verified_outlined,
          color: AppColors.green,
        ),
        MetricTile(
          label: 'Product pass',
          value: formatPercent(inspection.productPassRate),
          icon: Icons.shelves,
          color: AppColors.sky,
        ),
        MetricTile(
          label: 'Promo pass',
          value: formatPercent(inspection.promoPassRate),
          icon: Icons.local_offer_outlined,
          color: AppColors.orange,
        ),
      ],
    );
  }

  Widget _buildMissingItems(Inspection inspection) {
    if (inspection.missingItems.isEmpty) {
      return const EmptyState(
        icon: Icons.check_circle_outline,
        title: 'No missing items',
        message: 'The latest AI result did not report missing shelf items.',
      );
    }

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionTitle(
            title: 'Missing items (${inspection.missingItems.length})',
          ),
          const SizedBox(height: 12),
          ...inspection.missingItems.map((item) => MissingItemTile(item: item)),
        ],
      ),
    );
  }

  IconData _statusIcon(Inspection inspection) {
    if (inspection.isPass) return Icons.check_circle_outline;
    if (inspection.isWarning) return Icons.warning_amber_outlined;
    if (inspection.isFail || inspection.isRetake) return Icons.error_outline;
    return Icons.hourglass_top_rounded;
  }
}

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({required this.api, super.key});

  final ApiService api;

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  final TextEditingController _searchController = TextEditingController();
  late Future<List<Inspection>> _future;
  String _filter = 'ALL';

  static const List<String> _filters = [
    'ALL',
    'PASS',
    'WARNING',
    'FAIL',
    'PENDING',
  ];

  @override
  void initState() {
    super.initState();
    _future = widget.api.fetchInspections(limit: 100);
    _searchController.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    final next = widget.api.fetchInspections(limit: 100);
    setState(() => _future = next);
    await next;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Inspection History')),
      body: SafeArea(
        child: FutureBuilder<List<Inspection>>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting &&
                !snapshot.hasData) {
              return const LoadingView(message: 'Loading history...');
            }

            if (snapshot.hasError && !snapshot.hasData) {
              return ErrorView(
                message: 'Unable to load history.',
                detail: snapshot.error.toString(),
                onRetry: _reload,
              );
            }

            final inspections = _filtered(snapshot.data ?? <Inspection>[]);
            return RefreshIndicator(
              onRefresh: _reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 30),
                children: [
                  const PageIntro(
                    icon: Icons.history_rounded,
                    title: 'Inspection History',
                    subtitle:
                        'Search previous shelf audits and open detailed AI results.',
                  ),
                  const SizedBox(height: 16),
                  _buildControls(),
                  const SizedBox(height: 16),
                  if (inspections.isEmpty)
                    const EmptyState(
                      icon: Icons.manage_search_outlined,
                      title: 'No inspections found',
                      message: 'Try another search keyword or status filter.',
                    )
                  else
                    ...inspections.map(
                      (inspection) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: InspectionCard(
                          inspection: inspection,
                          onTap: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => ResultDetailScreen(
                                api: widget.api,
                                inspection: inspection,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  if (snapshot.hasError) ...[
                    const SizedBox(height: 4),
                    MessagePanel(
                      message:
                          'Showing cached list. Refresh failed: ${snapshot.error}',
                      isError: true,
                    ),
                  ],
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildControls() {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _searchController,
            decoration: const InputDecoration(
              hintText: 'Search by branch, model, result, or inspection ID',
              prefixIcon: Icon(Icons.search_rounded),
            ),
          ),
          const SizedBox(height: 12),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: _filters
                  .map(
                    (filter) => Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(filter),
                        selected: _filter == filter,
                        onSelected: (_) => setState(() => _filter = filter),
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ],
      ),
    );
  }

  List<Inspection> _filtered(List<Inspection> inspections) {
    final query = _searchController.text.trim().toLowerCase();
    return inspections.where((inspection) {
      final matchesFilter =
          _filter == 'ALL' || inspection.statusText == _filter;
      if (!matchesFilter) return false;
      if (query.isEmpty) return true;

      final searchable = [
        inspection.id?.toString(),
        inspection.branchCode,
        inspection.detectedModel,
        inspection.statusText,
        inspection.result,
      ].whereType<String>().join(' ').toLowerCase();
      return searchable.contains(query);
    }).toList();
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: AppColors.blue, size: 18),
          const SizedBox(width: 8),
          Text(
            '$label: ',
            style: const TextStyle(
              color: AppColors.muted,
              fontWeight: FontWeight.w800,
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              color: AppColors.ink,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}
