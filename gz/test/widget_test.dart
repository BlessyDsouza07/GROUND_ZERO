
import 'package:flutter_test/flutter_test.dart';
import 'package:groundzero/main.dart';

void main() {
  testWidgets('GroundZero app starts', (WidgetTester tester) async {
    await tester.pumpWidget(const GroundZeroApp());

    // Allow the initial app frame to render.
    await tester.pump();

    expect(find.byType(GroundZeroApp), findsOneWidget);
  });
}
