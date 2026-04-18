import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useLocation } from 'wouter';
import { useToast } from "@/hooks/use-toast";
import { useUser } from "@/contexts/UserContext"; // or wherever your auth context is


/**
 * Email Verification Page
 * 
 * Displays after user registration to verify their email address
 * Includes verification code input and resend functionality
 */
const EmailVerification = () => {
  const [verificationCode, setVerificationCode] = useState('');
  const [isVerifying, setIsVerifying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [email, setEmail] = useState('');
  const [, navigate] = useLocation();
  const { toast } = useToast();
  const [resendTimer, setResendTimer] = useState(60); // 60s countdown
  const [canResend, setCanResend] = useState(false);
  const { setUser, setIsAuthenticated, isAuthenticated, user, isRole } = useUser();

  // Set page title and get email
 useEffect(() => {
  document.title = "Verify Email - JobHive";

  const urlParams = new URLSearchParams(window.location.search);
  const urlEmail = urlParams.get("email");
  const storedEmail = localStorage.getItem("pendingVerificationEmail");

  const resolvedEmail = urlEmail || storedEmail;
  if (resolvedEmail) {
  setEmail(resolvedEmail);
  setCanResend(false);
  setResendTimer(60); // just start countdown without sending again
}

}, []);

useEffect(() => {
  let interval: NodeJS.Timeout;

  if (resendTimer > 0) {
    interval = setInterval(() => {
      setResendTimer((prev) => prev - 1);
    }, 1000);
  } else {
    setCanResend(true); // timer hit 0
  }

  return () => clearInterval(interval);
}, [resendTimer]);


const sendCodeAndStartTimer = async (targetEmail: string) => {
  const name = localStorage.getItem("registrationFullName");
  const password = localStorage.getItem("registrationPassword");
  const rawRole = localStorage.getItem("registrationAccountType");
  const role = rawRole === "student" ? "job_seeker" : "employer";


  if (!name || !password || !role || !targetEmail) {
    toast({
      title: "Missing Info",
      description: "Registration details are incomplete.",
      variant: "destructive",
    });
    return;
  }

  try {
    const res = await fetch("http://localhost:8000/api/send-verification-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, email: targetEmail, password, role }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Failed to resend code");
    }

    setCanResend(false);
    setResendTimer(60); // restart timer

    toast({
      title: "Verification code resent",
      description: data.message,
    });
  } catch (err: any) {
    toast({
      title: "Error",
      description: err.message,
      variant: "destructive",
    });
  }
};



  const handleVerificationCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/\D/g, '').slice(0, 6); // Only numbers, max 6 digits
    setVerificationCode(value);
  };



const handleVerifyEmail = async () => {
  if (verificationCode.length !== 6 || !email) return;

  setIsVerifying(true);

  try {
    // ─────────────────────────────────────────
    // STEP 1: Verify the code
    // ─────────────────────────────────────────
    const verifyRes = await fetch("http://localhost:8000/api/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code: verificationCode }),
    });

    const verifyData = await verifyRes.json();

    if (!verifyRes.ok || !verifyData.success) {
      toast({
        title: "Verification Failed",
        description: verifyData.error ?? "Incorrect or expired code.",
        variant: "destructive",
      });
      setIsVerifying(false);
      return;   // stop here — don't proceed to register
    }

    // ─────────────────────────────────────────
    // STEP 2: Register the account
    // ─────────────────────────────────────────
    const name     = localStorage.getItem("registrationFullName") ?? "";
    const password = localStorage.getItem("registrationPassword") ?? "";
    const rawRole  = localStorage.getItem("registrationAccountType") ?? "job_seeker";
    const role     = rawRole === "student" ? "job_seeker" : rawRole;

    const registerRes = await fetch("http://localhost:8000/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, password, role }),
    });

    const registerData = await registerRes.json();

    if (!registerRes.ok || !registerData.access_token) {
      toast({
        title: "Registration Failed",
        description: registerData.error ?? "Could not create account. Please try again.",
        variant: "destructive",
      });
      setIsVerifying(false);
      return;
    }

    // ─────────────────────────────────────────
    // STEP 3: Save session and redirect
    // ─────────────────────────────────────────
    localStorage.setItem("access_token", registerData.access_token);
    localStorage.setItem("JobHive_user", JSON.stringify(registerData.user));
    setUser(registerData.user);
    setIsAuthenticated(true);

    toast({
      title: "Welcome to JobHive! 🐝",
      description: "Your account has been created successfully.",
    });

    // Clean up temp data
    localStorage.removeItem("pendingVerificationEmail");
    localStorage.removeItem("registrationFullName");
    localStorage.removeItem("registrationPassword");
    localStorage.removeItem("registrationAccountType");

    // Redirect based on role
    if (rawRole === "employer") {
      navigate("/register/employer");
    } else {
      navigate("/register/student");
    }

  } catch (err) {
    toast({
      title: "Network Error",
      description: "Could not connect to server. Please try again.",
      variant: "destructive",
    });
  } finally {
    setIsVerifying(false);
  }
};


  const handleBackToRegister = () => {
    localStorage.removeItem('pendingVerificationEmail');
    localStorage.removeItem('registrationAccountType');
    localStorage.removeItem('registrationFullName');
    navigate('/register');
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] flex items-center justify-center px-4">
      <div className="max-w-md w-full space-y-8">
        {/* Logo and Header */}
        <div className="text-center">
          <div className="mx-auto h-12 w-12 bg-[#F6C500] rounded-lg flex items-center justify-center mb-6">
            <span className="text-black font-bold text-xl">🐝</span>
          </div>
          <h2 className="text-3xl font-bold text-gray-900 mb-2">
            Verify Your Email
          </h2>
          <p className="text-gray-600">
            We've sent a 6-digit verification code to
          </p>
          <p className="text-[#F6C500] font-semibold">
            {email || 'your email address'}
          </p>
        </div>

        {/* Verification Form */}
        <div className="bg-white py-8 px-6 shadow-lg rounded-lg">
          <div className="space-y-6">
            {/* Verification Code Input */}
            <div>
              <label htmlFor="verification-code" className="block text-sm font-medium text-gray-700 mb-2">
                Verification Code
              </label>
              <Input
                id="verification-code"
                type="text"
                placeholder="Enter 6-digit code"
                value={verificationCode}
                onChange={handleVerificationCodeChange}
                className="text-center text-2xl tracking-widest font-mono"
                maxLength={6}
                disabled={isVerifying}
              />
              <p className="text-xs text-gray-500 mt-1 text-center">
                Enter the 6-digit code sent to your email
              </p>
            </div>

            {/* Verify Button */}
            <Button
              onClick={handleVerifyEmail}
              disabled={verificationCode.length !== 6 || isVerifying}
              className="w-full bg-[#F6C500] hover:bg-[#E6B400] text-black font-semibold py-3"
            >
              {isVerifying ? (
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-black mr-2"></div>
                  Verifying...
                </div>
              ) : (
                'Verify Email'
              )}
            </Button>

            {/* Resend Code */}
            <div className="text-center">
  {canResend ? (
    <>
      <p className="text-sm text-gray-600 mb-3">Didn’t receive the code?</p>
      <Button
        variant="outline"
        onClick={() => sendCodeAndStartTimer(email)}
        disabled={isResending}
        className="text-[#F6C500] border-[#F6C500] hover:bg-[#FFFBEA]"
      >
        {isResending ? 'Sending...' : 'Resend Code'}
      </Button>
    </>
  ) : (
    <p className="text-sm text-gray-500">
      Code expires in <span className="font-semibold text-black">{resendTimer}s</span>
    </p>
  )}
</div>


            {/* Back to Register */}
            <div className="text-center border-t pt-4">
              <Button
                variant="ghost"
                onClick={handleBackToRegister}
                className="text-gray-600 hover:text-gray-800"
              >
                ← Back to Registration
              </Button>
            </div>
          </div>
        </div>

        {/* Help Text */}
        <div className="text-center">
          <p className="text-sm text-gray-500">
            Check your spam folder if you don't see the email.
          </p>
          <p className="text-sm text-gray-500 mt-1">
            For help, contact{' '}
            <a href="mailto:support@JobHive.com" className="text-[#F6C500] hover:underline">
              support@JobHive.com
            </a>
          </p>
        </div>
      </div>
    </div>
  );
};

export default EmailVerification;