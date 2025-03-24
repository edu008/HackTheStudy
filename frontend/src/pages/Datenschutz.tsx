import React from 'react';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import { useTranslation } from 'react-i18next';

const Datenschutz = () => {
  const { t } = useTranslation();
  
  return (
    <div className="min-h-screen flex flex-col bg-[#f0f7ff]">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-12 mt-20">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow-md border border-blue-100">
            <h1 className="text-3xl font-bold mb-8 text-gray-800 text-center">{t('legal.privacy.title')}</h1>
            
            <div className="space-y-8">
              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.responsibleTitle')} 📝</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.responsibleText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.dataCollectionTitle')} 📊</h2>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>{t('legal.privacy.dataRegistration')}</li>
                  <li>{t('legal.privacy.dataDocuments')}</li>
                  <li>{t('legal.privacy.dataUsage')}</li>
                  <li>{t('legal.privacy.dataTechnical')}</li>
                  <li>{t('legal.privacy.dataPayment')}</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.purposeTitle')} 🎯</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.purposeIntro')}
                </p>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>{t('legal.privacy.purposePlatform')}</li>
                  <li>{t('legal.privacy.purposeOptimization')}</li>
                  <li>{t('legal.privacy.purposePremium')}</li>
                  <li>{t('legal.privacy.purposeLegal')}</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.legalBasisTitle')} ⚖️</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.legalBasisText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.cookiesTitle')} 🍪</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.cookiesText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.apiTitle')} 🌐</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.apiText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.paymentTitle')} 💳</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.paymentText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.rightsTitle')} 📋</h2>
                <ul className="list-disc pl-6 text-gray-600 space-y-2">
                  <li>{t('legal.privacy.rightsAccess')}</li>
                  <li>{t('legal.privacy.rightsCorrection')}</li>
                  <li>{t('legal.privacy.rightsDeletion')}</li>
                  <li>{t('legal.privacy.rightsObjection')}</li>
                </ul>
                <p className="text-gray-600">
                  {t('legal.privacy.rightsContact')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.securityTitle')} 🔒</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.securityText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.privacy.retentionTitle')} 🕒</h2>
                <p className="text-gray-600">
                  {t('legal.privacy.retentionText')}
                </p>
              </section>
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default Datenschutz;