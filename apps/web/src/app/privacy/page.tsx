import Link from "next/link";

const SECTION_CLASS = "flex flex-col gap-2";
const HEADING_CLASS = "text-base font-semibold";
const BODY_CLASS = "text-sm leading-relaxed text-muted-foreground";

export default function PrivacyPolicyPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-8 px-4 py-12">
      <div className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-muted-foreground hover:underline">
          ← BizRadar 홈으로
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">개인정보처리방침</h1>
        <p className="text-sm text-muted-foreground">
          BizRadar(이하 &ldquo;서비스&rdquo;)는 「개인정보보호법」에 따라 이용자의
          개인정보를 보호하고 이와 관련한 고충을 신속하게 처리할 수 있도록 다음과 같이
          개인정보처리방침을 수립·공개합니다.
        </p>
      </div>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>1. 수집하는 개인정보 항목</h2>
        <p className={BODY_CLASS}>
          회원가입 시 이메일 주소, 비밀번호를 수집합니다. 비밀번호는 인증 서비스(Supabase
          Auth)에 의해 암호화되어 저장되며, 서비스는 평문 비밀번호를 저장하거나 조회할
          수 없습니다. 회사 프로필 입력 시 회사명, 직원 규모, 업종, 지역, 사업 형태,
          설립연도 등 사업자 정보를 추가로 수집하며, 이는 개인을 식별하기 위한 정보가
          아닌 매칭 서비스 제공을 위한 사업 정보입니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>2. 개인정보의 수집 및 이용 목적</h2>
        <p className={BODY_CLASS}>
          회원 식별 및 인증, 서비스 제공(공공 IT 프로젝트 매칭, 대시보드 제공), 이용자
          문의 대응을 위한 목적으로만 개인정보를 수집·이용합니다. 수집한 개인정보는
          명시한 목적 외의 용도로 이용하지 않습니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>3. 개인정보의 보유 및 이용 기간</h2>
        <p className={BODY_CLASS}>
          회원 탈퇴 시까지 보유하며, 탈퇴 요청 시 지체 없이 파기합니다. 관계 법령에 따라
          보존할 의무가 있는 경우 해당 법령에서 정한 기간 동안 보관합니다. 현재 서비스
          내 자체 탈퇴 기능은 준비 중이며, 탈퇴 및 개인정보 삭제를 원하시는 경우 아래
          연락처로 요청해주시면 지체 없이 처리합니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>4. 개인정보 처리위탁</h2>
        <p className={BODY_CLASS}>
          서비스는 안정적인 데이터베이스 운영 및 회원 인증을 위해 아래와 같이 개인정보
          처리업무를 위탁하고 있습니다.
        </p>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-3 py-2 font-medium">수탁자</th>
                <th className="px-3 py-2 font-medium">위탁업무 내용</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-2">Supabase, Inc.</td>
                <td className="px-3 py-2 text-muted-foreground">
                  데이터베이스 및 회원 인증(로그인) 인프라 운영
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>5. 개인정보의 국외 이전</h2>
        <p className={BODY_CLASS}>
          서비스는 데이터베이스 및 인증 인프라로 Supabase를 이용하며, 이 과정에서
          이용자의 개인정보가 국외 서버에 저장·처리될 수 있습니다. 국외 이전되는 항목,
          이전 국가, 수탁자, 이전 일시 및 방법 등 세부 내역은 이용 중인 Supabase 프로젝트
          리전 확정 후 본 방침에 구체적으로 반영합니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>6. 정보주체의 권리와 행사 방법</h2>
        <p className={BODY_CLASS}>
          이용자는 언제든지 자신의 개인정보에 대해 열람, 정정, 삭제, 처리정지를 요구할
          수 있습니다. 권리 행사는 아래 연락처를 통해 요청하실 수 있으며, 서비스는
          지체 없이 필요한 조치를 취합니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>7. 개인정보의 파기 절차 및 방법</h2>
        <p className={BODY_CLASS}>
          보유 기간이 경과하거나 처리 목적이 달성된 개인정보는 지체 없이 파기합니다.
          전자적 파일 형태의 정보는 복구 불가능한 방법으로 영구 삭제하며, 종이 문서로
          출력된 개인정보는 취급하지 않습니다.
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>8. 개인정보의 안전성 확보 조치</h2>
        <ul className={`${BODY_CLASS} list-inside list-disc`}>
          <li>비밀번호 암호화: 인증 서비스(Supabase Auth)가 비밀번호를 해싱하여 저장</li>
          <li>전송 구간 암호화: 모든 통신 구간에 HTTPS(TLS) 적용</li>
          <li>저장 데이터 암호화: 데이터베이스 인프라(Supabase) 차원의 저장 데이터 암호화</li>
          <li>
            접근 권한 통제: 행 단위 보안(Row Level Security)으로 각 회사는 자신의
            데이터에만 접근 가능하며, 다른 회사의 정보를 조회할 수 없음
          </li>
          <li>
            내부 키 관리: 서버 전용 관리자 키는 브라우저로 전송되지 않으며 별도 서버
            환경에서만 사용
          </li>
        </ul>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>9. 개인정보 보호책임자</h2>
        <p className={BODY_CLASS}>
          개인정보 처리에 관한 문의, 불만, 피해구제 등에 관한 사항은 아래로 연락해주시기
          바랍니다.
        </p>
        <p className={BODY_CLASS}>
          담당자: [담당자명] · 이메일: [연락처 이메일]
          <br />
          <span className="text-xs">
            (서비스 정식 출시 전 실제 담당자 정보로 교체가 필요합니다.)
          </span>
        </p>
      </section>

      <section className={SECTION_CLASS}>
        <h2 className={HEADING_CLASS}>10. 고지의 의무</h2>
        <p className={BODY_CLASS}>
          본 방침의 내용 추가, 삭제 및 수정이 있을 경우 시행일 최소 7일 전부터 서비스 내
          공지사항을 통해 고지합니다.
        </p>
        <p className={BODY_CLASS}>공고일자: [YYYY-MM-DD] · 시행일자: [YYYY-MM-DD]</p>
      </section>
    </main>
  );
}
