;; 1. Based on: 5
; $SIZE  MOD=23
$PROBLEM    PHENOBARB SIMPLE MODEL
$INPUT      ID TIME AMT WGT APGR DV FA1 FA2
$DATA      ../../../pheno.dta IGNORE=@
            ACCEPT=(ID.EQN.37,ID.EQN.38,ID.EQN.39,ID.EQN.40,ID.EQN.41,ID.EQN.42)
$SUBROUTINE ADVAN1 TRANS2
$PK


IF(AMT.GT.0) BTIME=TIME
TAD=TIME-BTIME
      TVCL=THETA(1)*WGT
      TVV=THETA(2)*WGT
IF(APGR.LT.5) TVV=TVV*(1+THETA(3))
      CL=TVCL*EXP(ETA(1))
      V=TVV*EXP(ETA(2))
      S1=V
$ERROR

      W=F
      Y=F+W*EPS(1)

      IPRED=F         ;  individual-specific prediction
      IRES=DV-IPRED   ;  individual-specific residual
      IWRES=IRES/W    ;  individual-specific weighted residual

$THETA  (0,0.00469555) ; POP_CL
$THETA  (0,0.984258) ; POP_V
$THETA  (-.99,0.15892)
$OMEGA  DIAGONAL(2)
 0.0293508  ;       IVCL
 0.027906  ;        IVV
$SIGMA  0.013241
$ESTIMATION METHOD=1 INTERACTION PRINT=1 MAXEVALS=0
$COVARIANCE UNCONDITIONAL
$TABLE      ID TIME AMT WGT APGR IPRED PRED TAD CWRES NPDE NOAPPEND
            NOPRINT ONEHEADER FILE=pheno_real.tab

