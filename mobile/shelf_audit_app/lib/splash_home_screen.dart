import 'package:flutter/material.dart';

import 'api_service.dart';
import 'app_theme.dart';
import 'inspection_models.dart';
import 'result_history_screens.dart';
import 'shared_widgets.dart';
import 'upload_screen.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    Future<void>.delayed(const Duration(milliseconds: 1100), () {
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacement(MaterialPageRoute(builder: (_) => const HomeScreen()));
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFFF7FAFF), Color(0xFFEFF7F2)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: const SafeArea(
          child: Center(
            child: Padding(
              padding: EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AppLogo(size: 104),
                  SizedBox(height: 24),
                  Text(
                    'Shelf Audit AI',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.ink,
                      fontSize: 32,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.2,
                    ),
                  ),
                  SizedBox(height: 8),
                  Text(
                    'AI-powered shelf inspection',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.muted,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  SizedBox(height: 34),
                  SizedBox(
                    width: 32,
                    height: 32,
                    child: CircularProgressIndicator(strokeWidth: 3),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ApiService _api = ApiService();
  late Future<List<Inspection>> _historyFuture;

  @override
  void initState() {
    super.initState();
    _historyFuture = _api.fetchInspections(limit: 100);
  }

  Future<void> _reload() async {
    final next = _api.fetchInspections(limit: 100);
    setState(() => _historyFuture = next);
    await next;
  }

  Future<void> _openUpload() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => UploadScreen(api: _api)));
    if (mounted) {
      setState(() => _historyFuture = _api.fetchInspections(limit: 100));
    }
  }

  Future<void> _openHistory() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => HistoryScreen(api: _api)));
    if (mounted) {
      setState(() => _historyFuture = _api.fetchInspections(limit: 100));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: FutureBuilder<List<Inspection>>(
          future: _historyFuture,
          builder: (context, snapshot) {
            final inspections = snapshot.data ?? <Inspection>[];
            return RefreshIndicator(
              onRefresh: _reload,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
                children: [
                  _buildHeader(),
                  const SizedBox(height: 20),
                  if (snapshot.connectionState == ConnectionState.waiting &&
                      inspections.isEmpty)
                    const LoadingView(message: 'Loading dashboard...')
                  else if (snapshot.hasError && inspections.isEmpty)
                    ErrorView(
                      message: 'Unable to load inspection history.',
                      detail: snapshot.error.toString(),
                      onRetry: _reload,
                    )
                  else ...[
                    _buildSummary(inspections),
                    const SizedBox(height: 18),
                    _buildActionCard(),
                    const SizedBox(height: 18),
                    _buildRecent(inspections),
                  ],
                  const SizedBox(height: 18),
                  Center(
                    child: Text(
                      'API: $apiBaseUrl',
                      style: TextStyle(
                        color: AppColors.muted.withValues(alpha: 0.80),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        const AppLogo(size: 58),
        const SizedBox(width: 14),
        const Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Shelf Audit',
                style: TextStyle(
                  color: AppColors.ink,
                  fontSize: 30,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -0.4,
                ),
              ),
              SizedBox(height: 3),
              Text(
                'Mobile AI inspection dashboard',
                style: TextStyle(
                  color: AppColors.muted,
                  fontSize: 14.5,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
        IconButton.filledTonal(
          onPressed: _reload,
          icon: const Icon(Icons.refresh),
          tooltip: 'Refresh',
        ),
      ],
    );
  }

  Widget _buildSummary(List<Inspection> inspections) {
    final total = inspections.length;
    final passed = inspections.where((item) => item.isPass).length;
    final failed = inspections
        .where((item) => item.isFail || item.isRetake)
        .length;
    final pending = inspections.where((item) => item.isPending).length;

    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      childAspectRatio: 1.55,
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      children: [
        SummaryCard(
          label: 'Total Inspections',
          value: '$total',
          icon: Icons.fact_check_outlined,
          color: AppColors.blue,
        ),
        SummaryCard(
          label: 'Passed',
          value: '$passed',
          icon: Icons.check_circle_outline,
          color: AppColors.green,
        ),
        SummaryCard(
          label: 'Failed',
          value: '$failed',
          icon: Icons.error_outline,
          color: AppColors.red,
        ),
        SummaryCard(
          label: 'Pending',
          value: '$pending',
          icon: Icons.hourglass_top,
          color: AppColors.orange,
        ),
      ],
    );
  }

  Widget _buildActionCard() {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.green.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(
                  Icons.camera_alt_outlined,
                  color: AppColors.green,
                ),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Start a shelf check',
                      style: TextStyle(
                        color: AppColors.ink,
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      'Capture or upload a shelf photo for AI inspection.',
                      style: TextStyle(
                        color: AppColors.muted,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          PrimaryButton(
            label: 'Start Shelf Inspection',
            icon: Icons.play_arrow_rounded,
            onPressed: _openUpload,
          ),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _openHistory,
            icon: const Icon(Icons.history_rounded),
            label: const Text('View History'),
          ),
        ],
      ),
    );
  }

  Widget _buildRecent(List<Inspection> inspections) {
    if (inspections.isEmpty) {
      return const EmptyState(
        icon: Icons.inventory_2_outlined,
        title: 'No inspections yet',
        message: 'Start the first shelf inspection to see recent results here.',
      );
    }

    final recent = inspections.first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SectionTitle(title: 'Recent inspection', actionText: 'History'),
        const SizedBox(height: 10),
        InspectionCard(
          inspection: recent,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ResultDetailScreen(api: _api, inspection: recent),
            ),
          ),
        ),
      ],
    );
  }
}
