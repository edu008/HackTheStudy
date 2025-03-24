import React from 'react';
import Navbar from '@/components/Navbar';
import Footer from '@/components/Footer';
import { useTranslation } from 'react-i18next';

const Impressum = () => {
  const { t } = useTranslation();
  
  return (
    <div className="min-h-screen flex flex-col bg-[#f0f7ff]">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-12 mt-20">
        <div className="max-w-3xl mx-auto">
          <div className="bg-white p-8 rounded-lg shadow-md border border-blue-100">
            <h1 className="text-3xl font-bold mb-8 text-gray-800 text-center">{t('legal.impressum.title')}</h1>
            
            <div className="space-y-8">
              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.impressum.infoTitle')}</h2>
                <p className="text-gray-600">
                  HackTheStudy<br />
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.impressum.contactTitle')}</h2>
                <p className="text-gray-600">
                  E-Mail: info.eduanroci@gmail.ch<br />
                </p>
              </section>


              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.impressum.responsibleTitle')}</h2>
                <p className="text-gray-600">
                  Eduan Roci<br />
                  {t('legal.impressum.country')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.impressum.disclaimerTitle')}</h2>
                <h3 className="text-lg font-medium mb-2 text-gray-700">{t('legal.impressum.liabilityContentTitle')}</h3>
                <p className="text-gray-600 mb-4">
                  {t('legal.impressum.liabilityContentText')}
                </p>
                
                <h3 className="text-lg font-medium mb-2 text-gray-700">{t('legal.impressum.liabilityLinksTitle')}</h3>
                <p className="text-gray-600">
                  {t('legal.impressum.liabilityLinksText')}
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold mb-4 text-gray-800">{t('legal.impressum.copyrightTitle')}</h2>
                <p className="text-gray-600">
                  {t('legal.impressum.copyrightText')}
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

export default Impressum;
